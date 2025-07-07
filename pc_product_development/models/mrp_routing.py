# -*- coding: utf-8 -*-

from odoo import api, fields, models

class MrpRoutingWorkcenter(models.Model):
    _inherit = 'mrp.routing.workcenter'
    
    operation_id = fields.Many2one('mrp.routing.workcenter.operation', string='Operation')

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

    name = fields.Char('Operation', required=True)
    workcenter_id = fields.Many2one('mrp.workcenter', 'Work Center', required=True, check_company=True, tracking=True)
    currency_id = fields.Many2one('res.currency', string='Currency')
    unit_price = fields.Monetary('Unit Price', currency_field='currency_id', tracking=True)
