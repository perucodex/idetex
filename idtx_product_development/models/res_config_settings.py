from odoo import fields, models, api

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    weaving_category_ids = fields.Many2many(related='company_id.weaving_category_ids', readonly=False)
    thread_category_ids = fields.Many2many(related='company_id.thread_category_ids', readonly=False)
