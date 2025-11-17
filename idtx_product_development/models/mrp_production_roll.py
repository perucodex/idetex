from odoo import _, models, fields, api

class MrpProductionRoll(models.Model):
    _inherit = "mrp.production.roll"

    theorical_length = fields.Float('Theorical Length', compute='_compute_theorical_lenght')

    @api.depends('production_id','product_id')
    def _compute_theorical_lenght(self):
        for rec in self:
            rec.theorical_length = rec.production_id.bom_id.technical_sheet_id.yield_meter * rec.gross_weight
