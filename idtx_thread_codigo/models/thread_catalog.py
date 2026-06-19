# -*- coding: utf-8 -*-
import logging
from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# Modelos de los 6 catálogos del Maestro de Código de Hilado. Son DEDICADOS
# (tablas propias, separadas de los catálogos de tejido product.title/fiber/...).
# Cada uno se siembra desde su tabla en la base SITPRO (mismo SQL Server que
# TEXPLUS) vía _sync_from_sitpro.

_SYNC_MODELS = [
    'product.thread.titulo', 'product.thread.cabos', 'product.thread.proceso',
    'product.thread.composicion', 'product.thread.linea', 'product.thread.diseno',
]


class ThreadCatalog(models.AbstractModel):
    _name = 'idtx.thread.catalog'
    _description = 'Catálogo de Hilado (base)'
    _order = 'code'
    _rec_names_search = ['code', 'name']  # desplegables Many2one buscan por código/desc.
    # (La barra de búsqueda de la lista usa la search view de thread_catalog_views.xml.)

    # Las subclases definen el origen en SITPRO:
    _sitpro_table = None       # p. ej. 'hil_titulo'
    _sitpro_code_col = None    # p. ej. 'cdgtitulo'
    _sitpro_name_col = None    # p. ej. 'titulo'
    _sitpro_name_len = None    # longitud de la columna nombre en SITPRO (trunca)

    code = fields.Char('Código', required=True, index=True)
    name = fields.Char('Descripción', required=True)
    active = fields.Boolean(default=True)

    @api.depends('code', 'name')
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = ("[%s] %s" % (rec.code, rec.name)) if rec.code else (rec.name or '')

    # ---- Escritura de vuelta a SITPRO (crea/modifica, NUNCA borra) ----

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        if not self.env.context.get('sitpro_no_writeback'):
            records._sitpro_upsert()
        return records

    def write(self, vals):
        do_sync = (('code' in vals or 'name' in vals)
                   and not self.env.context.get('sitpro_no_writeback'))
        # Captura los códigos viejos por si cambia el code (la PK en SITPRO).
        old_codes = {r.id: r.code for r in self} if (do_sync and 'code' in vals) else {}
        res = super().write(vals)
        if do_sync:
            self._sitpro_upsert(old_codes=old_codes)
        return res

    def action_open_delete_wizard(self):
        """Abre la 2ª confirmación (botón rojo, aviso de borrado definitivo +
        SITPRO) para los registros seleccionados. La 1ª confirmación la da el
        botón que llama aquí (atributo confirm)."""
        if not self:
            raise UserError(_("Selecciona al menos un registro para eliminar."))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Eliminar valor de catálogo'),
            'res_model': 'idtx.thread.catalog.delete.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_res_model': self._name,
                'default_res_ids': ','.join(str(i) for i in self.ids),
                'default_count': len(self),
            },
        }

    def unlink(self):
        # Prohíbe borrar valores en uso por productos/hilados.
        self._check_catalog_not_in_use()
        # Captura (tabla, columna_código, código) ANTES del unlink para borrar
        # también la fila en SITPRO (hil_*).
        to_delete = [
            (r._sitpro_table, r._sitpro_code_col, (r.code or '').strip())
            for r in self
            if r._sitpro_table and r._sitpro_code_col and (r.code or '').strip()
        ]
        res = super().unlink()
        if to_delete:
            self._sitpro_delete(to_delete)
        return res

    def _sitpro_delete(self, to_delete):
        """Borra en SITPRO (hil_*) los catálogos eliminados en Odoo. Si falla
        lanza UserError -> rollback de la transacción (revierte el unlink de
        Odoo). Respeta texplus_write_enabled (en dev el DELETE se descarta)."""
        conn = cursor = None
        try:
            conn = self.env['mrp.routing.workcenter.operation']._get_texplus_sql_connection()
            cursor = conn.cursor()
            for table, ccol, code in to_delete:
                cursor.execute(
                    "DELETE FROM SITPRO.dbo.%s WHERE [%s] = ?" % (table, ccol),
                    code)
            conn.commit()
            _logger.info("SITPRO delete %s: %d registro(s)", self._name, len(to_delete))
        except Exception as error:
            if conn:
                conn.rollback()
            raise UserError(_(
                "No se pudo eliminar el catálogo en SITPRO (%(t)s): %(e)s",
                t=self._description, e=error)) from error
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

    def _check_catalog_not_in_use(self):
        """Lanza UserError si algún registro de otro modelo (productos, hilados,
        …) referencia estos valores de catálogo vía Many2one almacenado."""
        if not self:
            return
        ref_fields = self.env['ir.model.fields'].sudo().search([
            ('relation', '=', self._name),
            ('ttype', '=', 'many2one'),
            ('store', '=', True),
        ])
        for f in ref_fields:
            Model = self.env.get(f.model)
            if Model is None or Model._abstract or Model._transient:
                continue
            if f.name not in Model._fields:
                continue
            used = Model.with_context(active_test=False).search_count([(f.name, 'in', self.ids)])
            if used:
                raise UserError(_(
                    "No se puede eliminar este valor de catálogo: hay %(n)s "
                    "registro(s) de «%(model)s» que lo usan.",
                    n=used, model=Model._description))

    def _sitpro_upsert(self, old_codes=None):
        """Inserta o actualiza estos registros en su tabla SITPRO (hil_*).
        Nunca borra. Si la escritura falla lanza UserError -> rollback de la
        transacción de Odoo (atómico). Respeta texplus_write_enabled: en dev el
        DML se descarta silenciosamente (conexión proxy de solo-lectura)."""
        targets = self.filtered(
            lambda r: r._sitpro_table and r._sitpro_code_col and r._sitpro_name_col)
        if not targets:
            return
        old_codes = old_codes or {}
        conn = cursor = None
        try:
            conn = self.env['mrp.routing.workcenter.operation']._get_texplus_sql_connection()
            cursor = conn.cursor()
            for rec in targets:
                table = rec._sitpro_table
                ccol = rec._sitpro_code_col
                ncol = rec._sitpro_name_col
                new_code = (rec.code or '').strip()
                if not new_code:
                    continue
                name = (rec.name or '').strip()
                if rec._sitpro_name_len:
                    name = name[:rec._sitpro_name_len]
                old_code = (old_codes.get(rec.id) or new_code).strip()
                # Nombres de tabla/columna son constantes del modelo (no input
                # de usuario); los valores van parametrizados.
                cursor.execute(
                    "SELECT 1 FROM SITPRO.dbo.%s WITH (NOLOCK) WHERE [%s] = ?" % (table, ccol),
                    old_code)
                if cursor.fetchone():
                    cursor.execute(
                        "UPDATE SITPRO.dbo.%s SET [%s] = ?, [%s] = ? WHERE [%s] = ?"
                        % (table, ccol, ncol, ccol),
                        new_code, name, old_code)
                else:
                    cursor.execute(
                        "INSERT INTO SITPRO.dbo.%s ([%s], [%s]) VALUES (?, ?)"
                        % (table, ccol, ncol),
                        new_code, name)
            conn.commit()
            _logger.info("SITPRO upsert %s: %d registro(s)", self._name, len(targets))
        except Exception as error:
            if conn:
                conn.rollback()
            raise UserError(_(
                "No se pudo actualizar el catálogo en SITPRO (%(t)s): %(e)s",
                t=self._description, e=error)) from error
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

    @api.model
    def _sync_from_sitpro(self):
        """Lee la tabla SITPRO de este catálogo y hace upsert por código.
        Devuelve (creados, actualizados)."""
        if not (self._sitpro_table and self._sitpro_code_col and self._sitpro_name_col):
            return (0, 0)
        # Estos create/write vienen DE SITPRO; no hay que reescribirlos allí.
        self = self.with_context(sitpro_no_writeback=True)
        conn = self.env['mrp.routing.workcenter.operation']._get_texplus_sql_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT [%s], [%s] FROM SITPRO.dbo.%s" % (
            self._sitpro_code_col, self._sitpro_name_col, self._sitpro_table))
        rows = cursor.fetchall()
        try:
            conn.close()
        except Exception:
            pass
        existing = {r.code: r for r in self.with_context(active_test=False).search([])}
        seen, to_create, updated = set(), [], 0
        for code, name in rows:
            code = (code or '').strip()
            name = (name or '').strip()
            if not code or code in seen:
                continue
            seen.add(code)
            rec = existing.get(code)
            if rec:
                if (rec.name or '') != (name or code):
                    rec.name = name or code
                    updated += 1
            else:
                to_create.append({'code': code, 'name': name or code})
        if to_create:
            self.create(to_create)
        _logger.info("SITPRO sync %s: +%d ~%d", self._name, len(to_create), updated)
        return (len(to_create), updated)

    @api.model
    def action_sync_all_from_sitpro(self):
        """Sincroniza los 6 catálogos desde SITPRO y muestra el resultado."""
        parts = []
        for model_name in _SYNC_MODELS:
            created, updated = self.env[model_name]._sync_from_sitpro()
            parts.append("%s: +%d ~%d" % (self.env[model_name]._description, created, updated))
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Sincronización SITPRO',
                'message': " | ".join(parts),
                'type': 'success',
                'sticky': True,
            },
        }


class ProductThreadTitulo(models.Model):
    _name = 'product.thread.titulo'
    _inherit = 'idtx.thread.catalog'
    _description = 'Hilado: Título'
    _sitpro_table = 'hil_titulo'
    _sitpro_code_col = 'cdgtitulo'
    _sitpro_name_col = 'titulo'
    _sitpro_name_len = 6
    _uniq_code = models.Constraint('unique(code)', 'Ya existe un título con ese código.')


class ProductThreadCabos(models.Model):
    _name = 'product.thread.cabos'
    _inherit = 'idtx.thread.catalog'
    _description = 'Hilado: Cabos'
    _sitpro_table = 'hil_cabos'
    _sitpro_code_col = 'cdgcabos'
    _sitpro_name_col = 'cabos'
    _sitpro_name_len = 50
    _uniq_code = models.Constraint('unique(code)', 'Ya existen cabos con ese código.')


class ProductThreadProceso(models.Model):
    _name = 'product.thread.proceso'
    _inherit = 'idtx.thread.catalog'
    _description = 'Hilado: Proceso'
    _sitpro_table = 'hil_proceso'
    _sitpro_code_col = 'cdgproceso'
    _sitpro_name_col = 'proceso'
    _sitpro_name_len = 50
    _uniq_code = models.Constraint('unique(code)', 'Ya existe un proceso con ese código.')


class ProductThreadComposicion(models.Model):
    _name = 'product.thread.composicion'
    _inherit = 'idtx.thread.catalog'
    _description = 'Hilado: Composición'
    _sitpro_table = 'hil_composicion'
    _sitpro_code_col = 'codigo'
    _sitpro_name_col = 'composicion'
    _sitpro_name_len = 70
    _uniq_code = models.Constraint('unique(code)', 'Ya existe una composición con ese código.')


class ProductThreadLinea(models.Model):
    _name = 'product.thread.linea'
    _inherit = 'idtx.thread.catalog'
    _description = 'Hilado: Línea'
    _sitpro_table = 'hil_linea'
    _sitpro_code_col = 'cdglinea'
    _sitpro_name_col = 'linea'
    _sitpro_name_len = 50
    _uniq_code = models.Constraint('unique(code)', 'Ya existe una línea con ese código.')


class ProductThreadDiseno(models.Model):
    _name = 'product.thread.diseno'
    _inherit = 'idtx.thread.catalog'
    _description = 'Hilado: Diseño'
    _sitpro_table = 'hil_diseno'
    _sitpro_code_col = 'codigo'
    _sitpro_name_col = 'composicion'
    _sitpro_name_len = 70
    _uniq_code = models.Constraint('unique(code)', 'Ya existe un diseño con ese código.')
