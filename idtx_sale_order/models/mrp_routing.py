# -*- coding: utf-8 -*-

from odoo import api, fields, models

class MrpRoutingWorkcenterOperation(models.Model):
    _inherit = 'mrp.routing.workcenter.operation'

    currency_id = fields.Many2one('res.currency', string='Currency', default=lambda self: self.env.ref('base.USD'))
    unit_price = fields.Monetary('Unit Price', currency_field='currency_id')
    type_prices = fields.Selection([
        ('pp', 'By Process'),
        ('col', 'By Color'),
    ], string='Type Prices', default = 'pp')
    per_title = fields.Boolean('Per Thread Title')
    product_color_price_ids = fields.One2many('product.color.price', 'mrwo_id', string='product_color_price')

    @api.onchange('type_prices')
    def _onchange_type_prices(self):
        for rec in self:
            if rec.type_prices == 'col':
                rec.unit_price = 0

class ProductColorPrice (models.Model):
    _name = 'product.color.price'
    _description = 'Product Color Price'

    mrwo_id = fields.Many2one('mrp.routing.workcenter.operation', string='mrp_routing_workcenter_operation')
    sequence = fields.Integer('sequence')
    product_color_id = fields.Many2one('product.color', string='Product Color')
    unit_price = fields.Monetary('Unit Price' , currency_field='currency_id')
    currency_id = fields.Many2one(related='mrwo_id.currency_id')
    color_title_price_ids = fields.One2many('product.color.title.price', 'pcp_id', string='Color Title Price')

class ProductColorTitlePrice(models.Model):
    _name = 'product.color.title.price'
    _description = 'Product Color Title Price'
    _rec_name = 'pcp_id'

    pcp_id = fields.Many2one('product.color.price', string='pcp')
    sequence = fields.Integer('sequence')
    title_ids = fields.Many2many('product.title', string='Titles')
    unit_price = fields.Monetary('Unit Price' , currency_field='currency_id')
    currency_id = fields.Many2one(related='pcp_id.currency_id')
