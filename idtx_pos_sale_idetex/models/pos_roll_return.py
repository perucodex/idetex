# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

class PosRollReturn(models.Model):
    _name = 'pos.roll.return'
    _description = 'Devolución de Rollos POS'
    _order = 'id desc'

    name = fields.Char(string='Referencia', required=True, copy=False, readonly=True, index=True, default=lambda self: _('Nuevo'))
    
    # Filtros y Selección
    pos_pack_lot_id = fields.Many2one('pos.pack.operation.lot', string='Rollo Original (Lote)', required=True)
    pos_order_line_id = fields.Many2one('pos.order.line', string='Línea de Venta', related='pos_pack_lot_id.pos_order_line_id', store=True)
    pos_order_id = fields.Many2one('pos.order', string='Documento (Venta)', related='pos_order_line_id.order_id', store=True)
    partner_id = fields.Many2one('res.partner', string='Cliente', related='pos_order_id.partner_id', store=True)
    product_id = fields.Many2one('product.product', string='Artículo', related='pos_order_line_id.product_id', store=True)
    
    # Datos del Rollo Original
    original_lot_name = fields.Char(string='Partida Original', related='pos_pack_lot_id.lot_name', store=True)
    color_code = fields.Char(string='Código de Color', compute='_compute_lot_data', store=True)
    color_name = fields.Char(string='Color', compute='_compute_lot_data', store=True)
    qty = fields.Float(string='Kilos', default=0.0)
    
    # Datos del Nuevo Rollo
    new_lot_name = fields.Char(string='Nuevo Rollo', store=True)
    
    # Estado y Trazabilidad
    picking_id = fields.Many2one('stock.picking', string='Movimiento de Reingreso', readonly=True)
    state = fields.Selection([
        ('draft', 'Borrador'),
        ('done', 'Reingresado')
    ], string='Estado', default='draft')

    @api.depends('original_lot_name')
    def _compute_lot_data(self):
        for rec in self:
            if rec.original_lot_name:
                lot = self.env['stock.lot'].search([('name', '=', rec.original_lot_name)], limit=1)
                if lot:
                    rec.color_code = lot.color_code
                    rec.color_name = lot.color_name
                else:
                    rec.color_code = False
                    rec.color_name = False
            else:
                rec.color_code = False
                rec.color_name = False

    @api.model_create_multi
    def create(self, vals_list):
        # Preparar lista de nombres originales para llamar a get_next_refund_lot_names una sola vez si es posible
        original_names = []
        for vals in vals_list:
            if vals.get('pos_pack_lot_id') and not vals.get('new_lot_name'):
                lot = self.env['pos.pack.operation.lot'].browse(vals['pos_pack_lot_id'])
                if lot and lot.lot_name:
                    original_names.append(lot.lot_name)
        
        # Obtener mapa de nuevos nombres
        next_names_map = {}
        if original_names:
            next_names_map = self.env['pos.order'].get_next_refund_lot_names(original_names)

        for vals in vals_list:
            # Correlativo DEV-POS
            if vals.get('name', _('Nuevo')) == _('Nuevo'):
                vals['name'] = self.env['ir.sequence'].next_by_code('pos.roll.return') or _('Nuevo')
            
            # Nuevo nombre de lote si no viene establecido
            if vals.get('pos_pack_lot_id') and not vals.get('new_lot_name'):
                lot = self.env['pos.pack.operation.lot'].browse(vals['pos_pack_lot_id'])
                if lot and lot.lot_name:
                    vals['new_lot_name'] = next_names_map.get(lot.lot_name, '')

        return super(PosRollReturn, self).create(vals_list)

    def action_return(self):
        self.ensure_one()
        if self.state == 'done':
            raise UserError(_('El rollo ya ha sido reingresado.'))
        if not self.new_lot_name:
            raise UserError(_('No se pudo generar el nuevo correlativo para el rollo.'))

        # Crear nuevo lote
        lot_vals = {
            'name': self.new_lot_name,
            'product_id': self.product_id.id,
            'company_id': self.env.company.id,
        }
        # Intentar pasar los campos de color si existen en stock.lot
        lot_model_fields = self.env['stock.lot']._fields
        if 'color_code' in lot_model_fields and self.color_code:
            lot_vals['color_code'] = self.color_code
        if 'color_name' in lot_model_fields and self.color_name:
            lot_vals['color_name'] = self.color_name

        # Enlazar al lote padre para trazabilidad (devolución textil:
        # el material devuelto es físicamente distinto del rollo original)
        if 'idtx_parent_lot_id' in lot_model_fields and self.original_lot_name:
            parent_lot = self.env['stock.lot'].search([
                ('name', '=', self.original_lot_name),
                ('product_id', '=', self.product_id.id),
            ], limit=1)
            if parent_lot:
                lot_vals['idtx_parent_lot_id'] = parent_lot.id

        new_lot = self.env['stock.lot'].create(lot_vals)

        # Buscar el tipo de operación "Devoluciones POS"
        picking_type = self.env['stock.picking.type'].search([
            ('name', 'ilike', 'Devoluciones POS'),
            ('company_id', '=', self.env.company.id)
        ], limit=1)
        
        if not picking_type:
            # Fallback a un tipo de entrada (Receipt)
            picking_type = self.env['stock.picking.type'].search([
                ('code', '=', 'incoming'),
                ('company_id', '=', self.env.company.id)
            ], limit=1)
            
        if not picking_type:
            raise UserError(_('No se encontró un tipo de operación "Devoluciones POS" ni un tipo de "Entrada" (Receipt) en el almacén.'))

        location_dest_id = picking_type.default_location_dest_id.id or self.env.ref('stock.stock_location_stock').id
        location_id = picking_type.default_location_src_id.id or self.env.ref('stock.stock_location_customers').id

        # Crear Picking
        picking_vals = {
            'picking_type_id': picking_type.id,
            'location_id': location_id,
            'location_dest_id': location_dest_id,
            'origin': f"Devolución POS: {self.pos_order_id.name}",
        }
        picking = self.env['stock.picking'].create(picking_vals)

        # Crear Move
        move_vals = {
            'description_picking': self.product_id.name,
            'product_id': self.product_id.id,
            'product_uom_qty': self.qty,
            'product_uom': self.product_id.uom_id.id,
            'picking_id': picking.id,
            'location_id': location_id,
            'location_dest_id': location_dest_id,
        }
        move = self.env['stock.move'].create(move_vals)

        # Crear Move Line con el nuevo lote
        move_line_vals = {
            'move_id': move.id,
            'product_id': self.product_id.id,
            'product_uom_id': self.product_id.uom_id.id,
            'quantity': self.qty,
            'lot_id': new_lot.id,
            'picking_id': picking.id,
            'location_id': location_id,
            'location_dest_id': location_dest_id,
        }
        self.env['stock.move.line'].create(move_line_vals)

        # Confirmar y validar el picking
        picking.action_confirm()
        picking.button_validate()

        self.write({
            'picking_id': picking.id,
            'state': 'done'
        })
