from odoo import fields, models, api

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    rotary_printing_min_qty = fields.Float(related='company_id.rotary_printing_min_qty', readonly=False)
    digital_printing_min_qty = fields.Float(related='company_id.digital_printing_min_qty', readonly=False)
    printing_currency_id = fields.Many2one(related='company_id.printing_currency_id', readonly=False)
    cylinder_64_price = fields.Monetary(related='company_id.cylinder_64_price', readonly=False, currency_field='printing_currency_id')
    cylinder_82_price = fields.Monetary(related='company_id.cylinder_82_price', readonly=False, currency_field='printing_currency_id')
    cylinder_102_price = fields.Monetary(related='company_id.cylinder_102_price', readonly=False, currency_field='printing_currency_id')
    sample_1_price = fields.Monetary(related='company_id.sample_1_price', readonly=False, currency_field='printing_currency_id')
    sample_2_price = fields.Monetary(related='company_id.sample_2_price', readonly=False, currency_field='printing_currency_id')
    sample_3_price = fields.Monetary(related='company_id.sample_3_price', readonly=False, currency_field='printing_currency_id')
    strike_off = fields.Monetary(related='company_id.strike_off', readonly=False, currency_field='printing_currency_id')