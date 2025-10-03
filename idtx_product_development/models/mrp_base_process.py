from odoo import fields, models

class MrpBaseProcess(models.Model):
    _name = 'mrp.base.process'
    _description = 'Mrp Base Process'

    name = fields.Char('Name')
    process_ids = fields.One2many('mrp.base.process.line', 'mrp_base_process_id', string='Process')

class MrpBaseProcessLine(models.Model):
    _name = 'mrp.base.process.line'
    _description = 'Mrp Base Process Line'

    mrp_base_process_id = fields.Many2one('mrp.base.process', string='Base Process')
    sequence = fields.Integer('sequence')
    operation_id = fields.Many2one('mrp.routing.workcenter.operation', string='Operation Name', ondelete='restrict')