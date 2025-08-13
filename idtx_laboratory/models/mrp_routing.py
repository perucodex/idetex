# -*- coding: utf-8 -*-

from odoo import api, fields, models

class MrpRoutingWorkcenter(models.Model):
    _inherit = 'mrp.routing.workcenter'
    
    operation_id = fields.Many2one('mrp.routing.workcenter.operation', string='Operation Name')

    @api.onchange('operation_id')
    def _onchange_operation_id(self):
        for rec in self:
            rec.name = rec.operation_id.name
            if rec.operation_id:
                rec.workcenter_id = rec.operation_id.workcenter_id

    @api.onchange('workcenter_id')
    def _onchange_workcenter_id(self):
        for rec in self:
            if rec.operation_id:
                if rec.workcenter_id and rec.workcenter_id != rec.operation_id.workcenter_id:
                    rec.operation_id = False

class MrpRoutingWorkcenterOperation(models.Model):
    _name = 'mrp.routing.workcenter.operation'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Workcenter Operation'

    name = fields.Char('Name', required=True)
    workcenter_id = fields.Many2one('mrp.workcenter', 'Work Center', required=True, check_company=True)
    currency_id = fields.Many2one('res.currency', string='Currency', default=lambda self: self.env.ref('base.USD'))
    unit_price = fields.Monetary('Unit Price', currency_field='currency_id')
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
        index=True,
        required=True
    )
    type_prices = fields.Selection([
        ('pp', 'Por Proceso'),
        ('col', 'Por Color'),
    ], string='Type Prices', default = 'pp')   
    product_color_price_ids = fields.One2many('product.color.price', 'mrwo_id', string='product_color_price')
    parameter_ids = fields.One2many('operation.parameter', 'operation_id', string='Parameters')
    is_weaving = fields.Boolean('Is Weaving?')

class ProductColorPrice (models.Model):
    _name = 'product.color.price'
    _description = 'Product Color Price'

    product_color_id = fields.Many2one('product.color', string='Product Color')
    unit_price = fields.Monetary('Unit Price' , currency_field='currency_id')
    mrwo_id = fields.Many2one('mrp.routing.workcenter.operation', string='mrp_rout_wngWorkcenter_operation')
    currency_id = fields.Many2one(related='mrwo_id.currency_id')

class OperationParameter(models.Model):
    _name = 'operation.parameter'
    _description = 'Operation Parameter'

    operation_id = fields.Many2one('mrp.routing.workcenter.operation', string='Operation')
    name = fields.Char('Name')
