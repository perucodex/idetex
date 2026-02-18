from odoo import fields, models, api

class ProductTemplate(models.Model):
    _inherit = 'product.template'

    is_rect = fields.Boolean(compute='_compute_is_rect')

    @api.depends('analysis_id')
    def _compute_is_rect(self):
        for rec in self:
            rec.is_rect = rec.analysis_id.weave_type == 'rect'