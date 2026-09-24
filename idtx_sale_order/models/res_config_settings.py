from odoo import fields, models, api

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'
    
    max_discount = fields.Float(related='company_id.max_discount', readonly=False)
    sales_pricelist_id = fields.Many2one(related='company_id.sales_pricelist_id', readonly=False)
    production_company_id = fields.Many2one(related='company_id.production_company_id', readonly=False)
    quotation_admin_approval = fields.Boolean(related='company_id.quotation_admin_approval', readonly=False)
    sale_admin_approval = fields.Boolean(related='company_id.sale_admin_approval', readonly=False)
    sale_finance_approval = fields.Boolean(related='company_id.sale_finance_approval', readonly=False)
    # Precios de muestra por defecto (JP, 23-sep-2026).
    sample_currency_id = fields.Many2one(related='company_id.sample_currency_id')
    sample_price = fields.Monetary(related='company_id.sample_price', readonly=False, currency_field='sample_currency_id')
    sample_printing_price = fields.Monetary(related='company_id.sample_printing_price', readonly=False, currency_field='sample_currency_id')
