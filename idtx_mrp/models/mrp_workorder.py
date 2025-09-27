from odoo import _, models, fields, api

class MrpWorkorder(models.Model):
    _inherit = 'mrp.workorder'

    mrwo_id = fields.Many2one('mrp.routing.workcenter.operation', string='Operation LAB')
    operation_type = fields.Selection(related='mrwo_id.operation_type')
    roll_ids = fields.One2many('mrp.workorder.roll', 'workorder_id', string='Weaving Rolls')
    batch_ids = fields.Many2many('mrp.workorder.batch', string='Batchs')
    equipment_ids = fields.Many2many('maintenance.equipment', string='Equipments')

    @api.onchange('mrwo_id')
    def _onchange_mrwo_id(self):
        for rec in self:
            rec.workcenter_id = rec.mrwo_id.workcenter_id
            rec.name = rec.mrwo_id.name