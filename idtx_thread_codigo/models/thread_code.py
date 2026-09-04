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

    # Atributos (catálogos dedicados de hilado)
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
    # descripción aunque el hilado esté creado.
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
        # Al editar la descripción se propaga al producto enlazado (su name).
        # La edición de la descripción de un hilado ya creado solo está
        # habilitada en la vista para el grupo "Manager de Hilado".
        if 'descripcion' in vals:
            for rec in self:
                if rec.product_id and rec.product_id.name != rec.descripcion:
                    rec.product_id.name = rec.descripcion
        return res

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
        return True

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
        """Revierte: borra el producto creado (simétrico al alta). Odoo impide
        el unlink (FK) si el producto ya tiene relaciones (stock.picking, etc.)."""
        self.ensure_one()
        if self.product_id:
            self.product_id.unlink()
        self.state = 'draft'
        return True

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
