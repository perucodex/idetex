from odoo import _, models, api
from odoo.exceptions import UserError

class MrpWorkorderRoll(models.Model):
    _inherit = "mrp.workorder.roll"

    def _sync_weaving_qty_produced(self, workorders):
        # No intentar ajustar qty_produced en WO cerradas: el core lo prohíbe.
        for workorder in workorders.exists().filtered(
            lambda wo: wo.operation_type == 'weaving' and wo.state not in ('done', 'cancel')
        ):
            workorder.qty_produced = sum(workorder.roll_ids.mapped('gross_weight'))

    def action_reprint_qr(self):
        if self.env.company.is_printer:
            self.workorder_id._print_zpl_to_network(self.workorder_id.create_zpl(self), self.env.company.zpl_printer_ip)

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for roll in records:
            if roll.workorder_id and roll.workorder_id.operation_type == 'weaving' and not roll.option_id:
                raise UserError(_('You must select an option before creating a weaving roll.'))
        workorders = records.mapped('workorder_id')
        workorders._sync_thread_consumption_from_rolls()
        records._sync_weaving_qty_produced(workorders)
        return records

    def write(self, vals):
        old_workorders = self.mapped('workorder_id')
        res = super().write(vals)

        workorders = old_workorders | self.mapped('workorder_id')
        fields_that_change_qty = {'gross_weight', 'quantity', 'workorder_id'}
        if {'gross_weight', 'option_id', 'workorder_id'} & set(vals.keys()):
            workorders._sync_thread_consumption_from_rolls()
        if fields_that_change_qty & set(vals.keys()):
            self._sync_weaving_qty_produced(workorders)
        return res

    def unlink(self):
        workorders = self.mapped('workorder_id')
        res = super().unlink()
        workorders._sync_thread_consumption_from_rolls()
        self._sync_weaving_qty_produced(workorders)
        return res