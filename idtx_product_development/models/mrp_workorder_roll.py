from odoo import _, models, fields

class MrpWorkorderRoll(models.Model):
    _inherit = "mrp.workorder.roll"

    technical_id = fields.Many2one(related='workorder_id.production_id.bom_id.technical_sheet_id')
    size_id = fields.Many2one('technical.size.line', string='size')
    weave_type = fields.Selection(related='workorder_id.weave_type')
    