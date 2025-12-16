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
    product_color_price_ids = fields.One2many('product.color.price', 'mrwo_id', string='product_color_price')

class ProductColorPrice (models.Model):
    _name = 'product.color.price'
    _description = 'Product Color Price'

    product_color_id = fields.Many2one('product.color', string='Product Color')
    unit_price = fields.Monetary('Unit Price' , currency_field='currency_id')
    mrwo_id = fields.Many2one('mrp.routing.workcenter.operation', string='mrp_routing_workcenter_operation')
    currency_id = fields.Many2one(related='mrwo_id.currency_id')
