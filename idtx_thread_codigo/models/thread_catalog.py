# -*- coding: utf-8 -*-
import logging
from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# Modelos de los 6 catálogos del Maestro de Código de Hilado. Son DEDICADOS
# (tablas propias, separadas de los catálogos de tejido product.title/fiber/...).
# Nacieron sembrados desde las tablas hil_* de SITPRO; desde 2026-09 se
# mantienen únicamente en Odoo (la sincronización con SITPRO se retiró).


class ThreadCatalog(models.AbstractModel):
    _name = 'idtx.thread.catalog'
    _description = 'Catálogo de Hilado (base)'
    _order = 'code'
    _rec_names_search = ['code', 'name']  # desplegables Many2one buscan por código/desc.
    # (La barra de búsqueda de la lista usa la search view de thread_catalog_views.xml.)

    code = fields.Char('Código', required=True, index=True)
    name = fields.Char('Descripción', required=True)
    active = fields.Boolean(default=True)

    @api.depends('code', 'name')
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = ("[%s] %s" % (rec.code, rec.name)) if rec.code else (rec.name or '')

    def action_open_delete_wizard(self):
        """Abre la 2ª confirmación (botón rojo, aviso de borrado definitivo)
        para los registros seleccionados. La 1ª confirmación la da el botón
        que llama aquí (atributo confirm)."""
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
        return super().unlink()

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


class ProductThreadTitulo(models.Model):
    _name = 'product.thread.titulo'
    _inherit = 'idtx.thread.catalog'
    _description = 'Hilado: Título'
    _uniq_code = models.Constraint('unique(code)', 'Ya existe un título con ese código.')


class ProductThreadCabos(models.Model):
    _name = 'product.thread.cabos'
    _inherit = 'idtx.thread.catalog'
    _description = 'Hilado: Cabos'
    _uniq_code = models.Constraint('unique(code)', 'Ya existen cabos con ese código.')


class ProductThreadProceso(models.Model):
    _name = 'product.thread.proceso'
    _inherit = 'idtx.thread.catalog'
    _description = 'Hilado: Proceso'
    _uniq_code = models.Constraint('unique(code)', 'Ya existe un proceso con ese código.')


class ProductThreadComposicion(models.Model):
    _name = 'product.thread.composicion'
    _inherit = 'idtx.thread.catalog'
    _description = 'Hilado: Composición'
    _uniq_code = models.Constraint('unique(code)', 'Ya existe una composición con ese código.')


class ProductThreadLinea(models.Model):
    _name = 'product.thread.linea'
    _inherit = 'idtx.thread.catalog'
    _description = 'Hilado: Línea'
    _uniq_code = models.Constraint('unique(code)', 'Ya existe una línea con ese código.')


class ProductThreadDiseno(models.Model):
    _name = 'product.thread.diseno'
    _inherit = 'idtx.thread.catalog'
    _description = 'Hilado: Diseño'
    _uniq_code = models.Constraint('unique(code)', 'Ya existe un diseño con ese código.')
