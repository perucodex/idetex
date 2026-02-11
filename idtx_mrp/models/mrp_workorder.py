from odoo import _, models, fields, api
from odoo.exceptions import UserError

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

    def unlink(self):
        for rec in self:
            if rec.state in ('done','progress'):
                raise UserError(_('You can\'t delete a workorder in state %s') % dict(rec._fields['state'].selection).get(rec.state, rec.state))
        return super().unlink()
    
    def button_reopen(self):
        self.ensure_one()
        self.leave_id.unlink()
        self.write({
            'state': 'ready',
            'date_finished': False,
        })
        return True
    
    def button_start(self, raise_on_invalid_state=False):
        for wo in self:
            if wo.workcenter_id.operation_type == 'weaving':
                if not wo.equipment_ids:
                    raise UserError(_('Please asign workorder equipments to work with.'))
                if not wo.employee_assigned_ids:
                    raise UserError(_('Please asign employees to the workorder.'))
        return super().button_start(raise_on_invalid_state=raise_on_invalid_state)