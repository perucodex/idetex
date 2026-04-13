from odoo import fields, models, api

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'
    
    max_discount = fields.Float(related='company_id.max_discount', readonly=False)
    sales_pricelist_id = fields.Many2one(related='company_id.sales_pricelist_id', readonly=False)