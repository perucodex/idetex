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


class OperationParameter(models.Model):
    _name = 'operation.parameter'
    _description = 'Operation Parameter'

    operation_id = fields.Many2one('mrp.routing.workcenter.operation', string='Operation')
    name = fields.Char('Name')
