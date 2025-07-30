from odoo import fields, models, api

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    weaving_category_ids = fields.One2many(related='company_id.weaving_category_ids', readonly=False)
    thread_category_ids = fields.One2many(related='company_id.thread_category_ids', readonly=False)

    @api.onchange('weaving_category_ids','thread_category_ids')
    def _onchange_weaving_thread_category(self):
        self.env['product.template'].search([])._compute_is_weaving_thread()