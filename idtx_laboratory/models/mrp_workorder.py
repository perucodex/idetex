from odoo import _, models, fields, api

class MrpWorkorder(models.Model):
    _inherit = "mrp.workorder"

    mrwo_id = fields.Many2one('mrp.routing.workcenter.operation', string='Operation')
    roll_ids = fields.One2many('mrp.workorder.roll', 'workorder_id', string='Weaving Rolls')
    weaving_wo = fields.Boolean(related='mrwo_id.is_weaving')
    weave_type = fields.Selection(related='product_id.product_tmpl_id.technical_sheet_id.weave_type')
    roll_weight = fields.Float('Roll Weight', compute='_compute_progress')
    quantity = fields.Float('Quantity', compute='_compute_progress')
    progress = fields.Float('Progress')

    @api.depends('roll_ids')
    def _compute_progress(self):
        for rec in self:
            if rec.weave_type == 'rect':
                rec.quantity = sum(rec.roll_ids.mapped('quantity'))
                rec.progress = (rec.quantity / rec.qty_remaining) * 100 if rec.qty_remaining else 100
                rec.roll_weight = 0
            else:
                rec.roll_weight = sum(rec.roll_ids.mapped('gross_weight'))
                rec.progress = (rec.roll_weight / rec.qty_remaining) * 100 if rec.qty_remaining else 100
                rec.quantity = 0

    @api.onchange('mrwo_id')
    def _onchange_mrwo_id(self):
        for rec in self:
            rec.name = rec.mrwo_id.name
            if rec.mrwo_id:
                rec.workcenter_id = rec.mrwo_id.workcenter_id
