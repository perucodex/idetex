# -*- coding: utf-8 -*-
from odoo import models, fields, api


_MOVEMENT_TYPES = [
    ('in',  'Entrada'),
    ('out', 'Salida'),
    ('int', 'Interno'),
    ('2q',  'Segunda Calidad'),
]


class ThreadLotControl(models.Model):
    _name = 'thread.lot.control'
    _description = 'Thread Lot Bag Control'
    _order = 'date desc, id desc'

    name = fields.Char(string='Reference', readonly=True, copy=False, default='/')
    date = fields.Date(string='Date', default=fields.Date.context_today)
    lot_id = fields.Many2one('stock.lot', string='Lot', required=True, index=True)
    product_id = fields.Many2one(
        'product.product', string='Product',
        related='lot_id.product_id', store=True,
    )
    company_id = fields.Many2one(
        'res.company', string='Company',
        related='lot_id.company_id', store=True,
    )
    movement_type = fields.Selection(_MOVEMENT_TYPES, string='Tipo Movimiento', required=True)
    source_location_id = fields.Many2one('stock.location', string='Source Location')
    dest_location_id   = fields.Many2one('stock.location', string='Destination Location')
    line_ids = fields.One2many('thread.lot.control.line', 'control_id', string='Bags')
    bag_count  = fields.Integer(compute='_compute_totals', string='Bag Count',  store=True)
    cone_count = fields.Integer(compute='_compute_totals', string='Cone Count', store=True)
    total_weight = fields.Float(compute='_compute_totals', string='Total Weight (kg)', store=True, digits=(12, 4))
    average_cone_weight = fields.Float(string='Avg Cone Weight (kg)', digits=(12, 4))
    note = fields.Text(string='Notes')

    @api.depends('line_ids.bag_qty', 'line_ids.cone_qty', 'line_ids.total_weight')
    def _compute_totals(self):
        for rec in self:
            rec.bag_count = sum(l.bag_qty for l in rec.line_ids)
            rec.cone_count = sum(l.bag_qty * l.cone_qty for l in rec.line_ids)
            rec.total_weight = sum(l.total_weight for l in rec.line_ids)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', '/') == '/':
                vals['name'] = self.env['ir.sequence'].next_by_code('thread.lot.control') or '/'
        return super().create(vals_list)


class ThreadLotControlLine(models.Model):
    _name = 'thread.lot.control.line'
    _description = 'Thread Lot Bag Control Line'
    _order = 'id'

    control_id = fields.Many2one('thread.lot.control', string='Control', required=True, ondelete='cascade', index=True)
    lot_id = fields.Many2one('stock.lot', string='Lot', related='control_id.lot_id', store=True)
    product_id = fields.Many2one('product.product', string='Product', related='control_id.product_id', store=True)
    date = fields.Date(string='Date', related='control_id.date', store=True)
    movement_type = fields.Selection(string='Tipo Movimiento', related='control_id.movement_type', store=True)
    source_location_id = fields.Many2one('stock.location', string='Source Location', related='control_id.source_location_id', store=True)
    dest_location_id   = fields.Many2one('stock.location', string='Destination Location', related='control_id.dest_location_id', store=True)
    bag_qty    = fields.Integer(string='Bag Qty', default=1)
    cone_qty   = fields.Integer(string='Cone Qty per Bag', default=0)
    cone_weight = fields.Float(string='Cone Weight (kg)', digits=(12, 4), default=0.0)
    total_weight = fields.Float(
        compute='_compute_cone_weight',
        string='Bag Weight (kg)',
        store=True, digits=(12, 4),
    )

    @api.depends('bag_qty', 'cone_qty', 'cone_weight')
    def _compute_cone_weight(self):
        for rec in self:
            rec.total_weight = rec.bag_qty * rec.cone_qty * rec.cone_weight
