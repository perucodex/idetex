from odoo import _, models, fields

class MrpWorkorder(models.Model):
    _inherit = 'mrp.workorder'

    mrwo_id = fields.Many2one('mrp.routing.workcenter.operation', string='Operation LAB')
    operation_type = fields.Selection(related='mrwo_id.operation_type')
    roll_ids = fields.One2many('mrp.workorder.roll', 'workorder_id', string='Weaving Rolls')
    batch_ids = fields.One2many('mrp.workorder.batch', 'workorder_id', string='Batchs')
    equipment_ids = fields.Many2many('maintenance.equipment', string='Equipments')