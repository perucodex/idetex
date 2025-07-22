from odoo import fields, models, api

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    chemical_category_ids = fields.One2many(related='company_id.chemical_category_ids', readonly=False)