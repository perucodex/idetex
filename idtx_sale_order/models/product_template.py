from odoo import fields, models, api

class ProductTemplate(models.Model):
    _inherit = 'product.template'

    is_rect = fields.Boolean(compute='_compute_is_rect')
    analysis_product_family_id = fields.Many2one(related='analysis_id.product_family_id', store=True, readonly=True, index=True)
    product_title_id = fields.Many2one(related='analysis_id.product_title_id', store=True, readonly=True, index=True)
    density = fields.Integer(related='analysis_id.density', store=True, readonly=True, index=True)
    standard_width = fields.Float(related='analysis_id.standard_width', store=True, readonly=True, index=True)

    @api.depends('analysis_id')
    def _compute_is_rect(self):
        for rec in self:
            rec.is_rect = rec.analysis_id.weave_type == 'rect'