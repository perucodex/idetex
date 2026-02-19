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
    fas_code = fields.Char('Código MSSQL', help="Código correspondiente en la tabla FASPRO de MSSQL")
    workcenter_id = fields.Many2one('mrp.workcenter', 'Work Center', required=True, check_company=True)
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
        index=True,
        required=True
    )
    parameter_ids = fields.One2many('operation.parameter', 'operation_id', string='Parameters')
    operation_type = fields.Selection(related='workcenter_id.operation_type')

class OperationParameter(models.Model):
    _name = 'operation.parameter'
    _description = 'Operation Parameter'

    operation_id = fields.Many2one('mrp.routing.workcenter.operation', string='Operation')
    name = fields.Char('Name')
