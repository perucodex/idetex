from odoo import _, models, fields, api
from odoo.exceptions import UserError

class MrpWorkorderRoll(models.Model):
    _name = "mrp.workorder.roll"
    _description = 'Mrp Workorder Roll'

    workorder_id = fields.Many2one('mrp.workorder', string='Workorder')
    sequence = fields.Integer('Sequence')
    name = fields.Char('Number') #, compute='_compute_roll_name', store=True)
    uom_id = fields.Many2one(related='workorder_id.product_id.product_tmpl_id.uom_id')
    technical_id = fields.Many2one(related='workorder_id.production_id.bom_id.technical_sheet_id')
    size_id = fields.Many2one('technical.size.line', string='size')
    quantity = fields.Integer('Quantity')
    gross_weight = fields.Float('Gross Weight')
    net_weight = fields.Float('Net Weight')
    in_batch = fields.Boolean('in_batch?', default=False)
    new_weight = fields.Float('Split new weight')
    weave_type = fields.Selection(related='workorder_id.weave_type')
    equipment_id = fields.Many2one('maintenance.equipment', string='Equipment')
    employee_id = fields.Many2one('hr.employee', string='Employee')
    
    # @api.depends('equipment_id','employee_id','sequence')
    # def _compute_roll_name(self):
    #     for rec in self:
    #         rec.name = str(rec.equipment_id.id).zfill(3) + str(rec.employee_id.id).zfill(3) +  str(rec.sequence + 1).zfill(3)

    #=== CRUD METHODS ===#

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            vals['name'] = self.env['ir.sequence'].with_company(vals.get('company_id')).next_by_code('mrp.workorder.roll')
        return super().create(vals_list)
    
    def unlink(self):
        roll_names = ''
        for rec in self:
            if rec.in_batch:
                roll_names += rec.name + '\n'
        if roll_names:
            raise UserError(_('Can\'t delete a roll that is in a batch process.\nRolls:\n%s') %roll_names)
        return super().unlink()

    def split(self):
        return {
            'name': _('Divide Roll'),
            'view_mode': 'form',
            'res_model': 'split.roll',
            'views': [(self.env.ref('idtx_laboratory.split_roll_form').id, 'form')],
            'type': 'ir.actions.act_window',
            'target': 'new',
            'context': dict(self.env.context), #, active_ids=to_merge.ids),
        }
