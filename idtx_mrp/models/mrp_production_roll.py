from odoo import _, models, fields, api
from odoo.exceptions import UserError

class MrpProductionRoll(models.Model):
    _name = "mrp.production.roll"
    _description = 'Mrp Production Roll'

    production_id = fields.Many2one('mrp.production', string='Production')
    sequence = fields.Integer('Sequence')
    batch_id = fields.Many2one('mrp.workorder.batch', string='Batch')
    name = fields.Char('Number')
    product_id = fields.Many2one(related='production_id.product_id.product_tmpl_id')
    uom_id = fields.Many2one(related='production_id.product_id.product_tmpl_id.uom_id')
    quantity = fields.Integer('Quantity')
    gross_weight = fields.Float('Gross Weight')
    net_weight = fields.Float('Net Weight')
    net_length = fields.Float('Net Length')
    theorical_length = fields.Float('Theorical Length', compute='_compute_theorical_lenght')
    # in_batch = fields.Boolean('in_batch?', default=False)
    # new_weight = fields.Float('Split new weight')
    equipment_id = fields.Many2one('maintenance.equipment', string='Equipment')
    employee_id = fields.Many2one('hr.employee', string='Employee')

    # TODO calcula desde la ficha tecnica
    @api.depends('product_id')
    def _compute_theorical_lenght(self):
        for rec in self:
            rec.theorical_length = 0

    #=== CRUD METHODS ===#

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            vals['name'] = self.env['ir.sequence'].with_company(vals.get('company_id')).next_by_code('mrp.production.roll')
        return super().create(vals_list)