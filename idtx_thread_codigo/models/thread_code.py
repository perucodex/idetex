# -*- coding: utf-8 -*-
import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class ThreadCode(models.Model):
    _name = 'idtx.thread.code'
    _description = 'Hilado (Maestro de Código)'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc'

    name = fields.Char('Nombre', compute='_compute_name', store=True)
    codigo = fields.Char('Código', compute='_compute_codigo', store=True, readonly=True)
    descripcion = fields.Char('Descripción', required=True)
    # descrip2 = fields.Char('Descripción 2')

    # Atributos (catálogos dedicados, sembrados desde SITPRO)
    thread_titulo_id = fields.Many2one('product.thread.titulo', string='Título', required=True)
    thread_cabos_id = fields.Many2one('product.thread.cabos', string='Cabos', required=True)
    thread_proceso_id = fields.Many2one('product.thread.proceso', string='Proceso', required=True)
    thread_composicion_id = fields.Many2one('product.thread.composicion', string='Composición')
    thread_linea_id = fields.Many2one('product.thread.linea', string='Línea', required=True)
    # Diseño y composición son OPCIONALES: los códigos reales de codigohilocrud
    # (p. ej. 0201CA114) no siempre los llevan.
    thread_diseno_id = fields.Many2one('product.thread.diseno', string='Diseño')
    thread_desarrollo = fields.Boolean('Desarrollo')

    state = fields.Selection(
        [('draft', 'Borrador'), ('created', 'Creado')],
        default='draft', required=True, copy=False, tracking=True)
    product_id = fields.Many2one('product.template', string='Producto', copy=False, readonly=True)
    product_count = fields.Integer(compute='_compute_product_count')
    # True si el usuario actual es "Manager de Hilado": puede editar la
    # descripción aunque el hilado esté creado (y el cambio va a SITPRO).
    user_is_thread_manager = fields.Boolean(compute='_compute_user_is_thread_manager')

    @api.depends_context('uid')
    def _compute_user_is_thread_manager(self):
        is_mgr = self.env.user.has_group('idtx_thread_codigo.group_thread_manager')
        for rec in self:
            rec.user_is_thread_manager = is_mgr

    @api.depends('thread_titulo_id', 'thread_cabos_id', 'thread_proceso_id',
                 'thread_linea_id', 'thread_composicion_id', 'thread_diseno_id')
    def _compute_codigo(self):
        for rec in self:
            rec.codigo = "".join([
                rec.thread_titulo_id.code or '',
                rec.thread_cabos_id.code or '',
                rec.thread_proceso_id.code or '',
                rec.thread_linea_id.code or '',
                rec.thread_composicion_id.code or '',
                rec.thread_diseno_id.code or '',
            ])

    @api.depends('codigo', 'descripcion')
    def _compute_name(self):
        for rec in self:
            if rec.codigo:
                rec.name = "[%s] %s" % (rec.codigo, rec.descripcion or '')
            else:
                rec.name = rec.descripcion or _('Nuevo')

    @api.depends('product_id')
    def _compute_product_count(self):
        for rec in self:
            rec.product_count = 1 if rec.product_id else 0

    # @api.model
    # def _import_clean_from_sitpro(self):
    #     """Importación única (post_init / migración): crea un idtx.thread.code por
    #     cada hilado de SITPRO.codigohilocrud cuyo código se REGENERA EXACTO desde
    #     los catálogos. El código es titulo+cabo+proceso+linea+composicion+diseño;
    #     composición se sabe por columna y el sobrante final del código es el
    #     diseño (si es un código válido de hil_diseno). Se omiten las filas con
    #     catálogo faltante o cuyo sobrante no es un diseño conocido (códigos
    #     heredados, p. ej. con fibra).

    #     Enlaza al product.template por default_code si existe; si no, lo crea.
    #     NO escribe en SITPRO (los datos ya están allí: se crea el product.template
    #     directamente, sin pasar por action_create_product/_create_in_sitpro).
    #     Idempotente: salta los códigos que ya tienen un idtx.thread.code.
    #     Devuelve un dict de contadores."""
    #     def code_map(model_name):
    #         return {r.code: r.id for r in
    #                 self.env[model_name].with_context(active_test=False).search([])}
    #     m_tit = code_map('product.thread.titulo')
    #     m_cab = code_map('product.thread.cabos')
    #     m_pro = code_map('product.thread.proceso')
    #     m_lin = code_map('product.thread.linea')
    #     m_com = code_map('product.thread.composicion')
    #     m_dis = code_map('product.thread.diseno')

    #     conn = self.env['mrp.routing.workcenter.operation']._get_texplus_sql_connection()
    #     cursor = conn.cursor()
    #     cursor.execute(
    #         "SELECT codigo, titulo, cabo, proceso, linea, composicion, descrip, "
    #         "descrip2, desarrollo FROM SITPRO.dbo.codigohilocrud")
    #     rows = cursor.fetchall()
    #     try:
    #         conn.close()
    #     except Exception:
    #         pass

    #     existing = set(self.with_context(active_test=False).search([]).mapped('codigo'))
    #     Product = self.env['product.template']
    #     created = with_diseno = linked = created_prod = skipped_recon = skipped_cat = 0
    #     seen = set()
    #     for row in rows:
    #         cod = (row.codigo or '').strip()
    #         if not cod or cod in seen:
    #             continue
    #         seen.add(cod)
    #         if cod in existing:
    #             continue  # idempotente
    #         t = (row.titulo or '').strip()
    #         c = (row.cabo or '').strip()
    #         p = (row.proceso or '').strip()
    #         l = (row.linea or '').strip()
    #         co = (row.composicion or '').strip()
    #         # 1) catálogos obligatorios presentes (composición opcional, pero si
    #         #    viene debe existir para que el código compute igual)
    #         if not (t in m_tit and c in m_cab and p in m_pro and l in m_lin
    #                 and (not co or co in m_com)):
    #             skipped_cat += 1
    #             continue
    #         # 2) El código = titulo+cabo+proceso+linea+composicion + (diseño opc).
    #         #    La composición la sabemos por columna; lo que sobra al final del
    #         #    código es el diseño (debe ser un código válido de hil_diseno).
    #         prefix = t + c + p + l + co
    #         if not cod.startswith(prefix):
    #             skipped_recon += 1
    #             continue
    #         diseno = cod[len(prefix):]
    #         if diseno and diseno not in m_dis:
    #             # El sobrante no es un diseño conocido (p. ej. códigos heredados
    #             # que incluyen la fibra); no se puede representar, se omite.
    #             skipped_recon += 1
    #             continue
    #         desc = (row.descrip or '').strip() or (row.descrip2 or '').strip() or cod
    #         tc = self.create({
    #             'descripcion': desc,
    #             'thread_titulo_id': m_tit[t],
    #             'thread_cabos_id': m_cab[c],
    #             'thread_proceso_id': m_pro[p],
    #             'thread_linea_id': m_lin[l],
    #             'thread_composicion_id': m_com.get(co) if co else False,
    #             'thread_diseno_id': m_dis[diseno] if diseno else False,
    #             'thread_desarrollo': bool(row.desarrollo),
    #         })
    #         created += 1
    #         if diseno:
    #             with_diseno += 1
    #         # Enlaza al producto existente o lo crea (sin escribir en SITPRO).
    #         product = Product.search([('default_code', '=', cod)], limit=1)
    #         if product:
    #             linked += 1
    #         else:
    #             product = Product.create(tc._thread_product_vals())
    #             created_prod += 1
    #         tc.product_id = product.id
    #         tc.state = 'created'
    #     _logger.info(
    #         "Importación hilados SITPRO: %s hilados creados (%s con diseño; %s "
    #         "productos enlazados, %s productos creados); omitidos %s por código "
    #         "no parseable, %s por catálogo faltante.",
    #         created, with_diseno, linked, created_prod, skipped_recon, skipped_cat)
    #     return {
    #         'created': created, 'with_diseno': with_diseno, 'linked': linked,
    #         'created_products': created_prod, 'skipped_unparseable': skipped_recon,
    #         'skipped_catalog': skipped_cat,
    #     }

    @api.onchange('thread_titulo_id', 'thread_cabos_id', 'thread_composicion_id', 'thread_proceso_id')
    def _onchange_suggest_descripcion(self):
        # Propone una descripción si está vacía (editable después).
        for rec in self:
            if rec.thread_titulo_id and rec.thread_cabos_id:
                # comp = (' ' + rec.thread_composicion_id.name) if rec.thread_composicion_id else ''
                rec.descripcion = "HILO %s/" % (
                    rec.thread_titulo_id.code or '')

    def _thread_product_vals(self):
        self.ensure_one()
        thread_category = self.env.ref('idtx_product_development.product_categ_2')
        return {
            'name': self.descripcion,
            'default_code': self.codigo,
            'categ_id': thread_category.id,
            'thread_titulo_id': self.thread_titulo_id.id,
            'thread_cabos_id': self.thread_cabos_id.id,
            'thread_proceso_id': self.thread_proceso_id.id,
            'thread_composicion_id': self.thread_composicion_id.id,
            'thread_linea_id': self.thread_linea_id.id,
            'thread_diseno_id': self.thread_diseno_id.id,
            'thread_desarrollo': self.thread_desarrollo,
            # 'thread_descrip2': self.descrip2,
        }

    def write(self, vals):
        res = super().write(vals)
        # Al editar la descripción se propaga al producto enlazado (su name) y al
        # maestro VFP en SITPRO. La edición de la descripción de un hilado ya
        # creado solo está habilitada en la vista para el grupo "Manager de Hilado".
        if 'descripcion' in vals:
            for rec in self:
                if rec.product_id and rec.product_id.name != rec.descripcion:
                    rec.product_id.name = rec.descripcion
                if rec.state == 'created' and rec.codigo:
                    rec._update_descripcion_in_sitpro()
        return res

    def _update_descripcion_in_sitpro(self):
        """Actualiza descrip/descrip2 en SITPRO.dbo.codigohilocrud para este
        hilado. Si falla lanza UserError -> rollback de la transacción de Odoo.
        Respeta texplus_write_enabled (en dev el UPDATE se descarta)."""
        self.ensure_one()
        if not self.codigo:
            return
        conn = cursor = None
        try:
            conn = self.env['mrp.routing.workcenter.operation']._get_texplus_sql_connection()
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE SITPRO.dbo.codigohilocrud SET descrip = ?, descrip2 = ? "
                "WHERE codigo = ?",
                (self.descripcion or '')[:90],
                (self.descripcion or '')[:50],
                self.codigo,
            )
            conn.commit()
            _logger.info(
                "Hilado: descripción de %s actualizada en SITPRO.codigohilocrud",
                self.codigo)
        except Exception as error:
            if conn:
                conn.rollback()
            raise UserError(_(
                "No se pudo actualizar la descripción en SITPRO "
                "(codigohilocrud): %s") % error) from error
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

    def action_create_product(self):
        self.ensure_one()
        if self.product_id:
            raise UserError(_("Este hilado ya tiene un producto creado."))
        if not self.codigo:
            raise UserError(_("Faltan atributos para generar el código."))
        # Odoo solo avisa de referencias duplicadas con un onchange (no se dispara
        # al crear por código), así que aquí lo validamos explícitamente.
        duplicate = self.env['product.template'].search(
            [('default_code', '=', self.codigo)], limit=1)
        if duplicate:
            raise UserError(_(
                "La referencia interna '%(code)s' ya existe en el producto "
                "'%(name)s'.", code=self.codigo, name=duplicate.display_name))
        product = self.env['product.template'].create(self._thread_product_vals())
        self.product_id = product
        self.state = 'created'
        # Replica el alta en el maestro VFP (SITPRO.codigohilocrud). Si falla
        # lanza UserError -> rollback de toda la transacción (no queda el
        # producto Odoo sin su contraparte en SITPRO).
        self._create_in_sitpro()
        return True

    def _create_in_sitpro(self):
        """Inserta este hilado en SITPRO.dbo.codigohilocrud (maestro VFP).

        - Si el código ya existe en SITPRO, o la escritura falla, lanza
          UserError; la transacción de Odoo se revierte.
        - En instancias con texplus_write_enabled=False el INSERT se descarta
          silenciosamente (protección de producción) y el producto Odoo sí se
          crea; la conexión devuelta es un proxy de solo-lectura.
        """
        self.ensure_one()
        conn = cursor = None
        try:
            conn = self.env['mrp.routing.workcenter.operation']._get_texplus_sql_connection()
            cursor = conn.cursor()
            cursor.execute(
                "SELECT 1 FROM SITPRO.dbo.codigohilocrud WITH (NOLOCK) WHERE codigo = ?",
                self.codigo,
            )
            if cursor.fetchone():
                raise UserError(_(
                    "El código '%s' ya existe en SITPRO (codigohilocrud); "
                    "no se puede crear de nuevo.") % self.codigo)
            cursor.execute(
                "INSERT INTO SITPRO.dbo.codigohilocrud "
                "(codigo, descrip, descrip2, titulo, cabo, proceso, linea, "
                "composicion, desarrollo, estado, feccrea, usuario) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                self.codigo,
                (self.descripcion or '')[:90],
                (self.descripcion or '')[:50],
                (self.thread_titulo_id.code or '')[:10],
                (self.thread_cabos_id.code or '')[:50],
                (self.thread_proceso_id.code or '')[:50],
                (self.thread_linea_id.code or '')[:50],
                (self.thread_composicion_id.code or '')[:90],
                1 if self.thread_desarrollo else 0,
                1,
                fields.Datetime.now(),
                (self.env.user.login or '')[:50],
            )
            conn.commit()
            _logger.info(
                "Hilado: código %s insertado en SITPRO.codigohilocrud", self.codigo)
        except UserError:
            if conn:
                conn.rollback()
            raise
        except Exception as error:
            if conn:
                conn.rollback()
            raise UserError(_(
                "No se pudo crear el hilado en SITPRO (codigohilocrud): %s") % error) from error
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

    def action_return_open_wizard(self):
        """Tras la 1ª confirmación del botón, abre el wizard de 2ª confirmación
        (botón rojo, aviso de borrado definitivo) antes de revertir."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Revertir hilado'),
            'res_model': 'idtx.thread.code.return.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_thread_code_id': self.id},
        }

    def action_return(self):
        """Revierte: borra el producto creado y la fila en SITPRO (simétrico al
        alta). Odoo impide el unlink (FK) si el producto ya tiene relaciones
        (stock.picking, etc.)."""
        self.ensure_one()
        if self.product_id:
            self.product_id.unlink()
        self._delete_in_sitpro()
        self.state = 'draft'
        return True

    def _delete_in_sitpro(self):
        """Borra este hilado de SITPRO.dbo.codigohilocrud (simétrico a
        _create_in_sitpro). Si la escritura falla lanza UserError -> rollback de
        la transacción de Odoo. En instancias con texplus_write_enabled=False el
        DELETE se descarta silenciosamente.
        """
        self.ensure_one()
        if not self.codigo:
            return
        conn = cursor = None
        try:
            conn = self.env['mrp.routing.workcenter.operation']._get_texplus_sql_connection()
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM SITPRO.dbo.codigohilocrud WHERE codigo = ?",
                self.codigo,
            )
            conn.commit()
            _logger.info(
                "Hilado: código %s eliminado de SITPRO.codigohilocrud", self.codigo)
        except Exception as error:
            if conn:
                conn.rollback()
            raise UserError(_(
                "No se pudo revertir el hilado en SITPRO (codigohilocrud): %s") % error) from error
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

    def action_open_product(self):
        self.ensure_one()
        if not self.product_id:
            return False
        return {
            'type': 'ir.actions.act_window',
            'name': _('Producto'),
            'res_model': 'product.template',
            'res_id': self.product_id.id,
            'view_mode': 'form',
            'target': 'current',
        }
