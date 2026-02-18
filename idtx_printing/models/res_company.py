from odoo import fields, models, api

class ResCompany(models.Model):
    _inherit = 'res.company'

    rotary_printing_min_qty = fields.Float('Rotary Printing Min. Qty.')
    digital_printing_min_qty = fields.Float('Digital Printing Min. Qty.')
    printing_currency_id = fields.Many2one('res.currency', string='Printing Currency', default=lambda self: self.env.ref('base.USD'))
    cylinder_64_price = fields.Monetary('Cilinder Raport 64 Price')
    cylinder_82_price = fields.Monetary('Cilinder Raport 82 Price')
    cylinder_102_price = fields.Monetary('Cilinder Raport 102 Price')
    sample_1_price = fields.Monetary('Sample Price from 0 to 100 mts')
    sample_2_price = fields.Monetary('Sample Price from 101 to 200 mts')
    sample_3_price = fields.Monetary('Sample Price from 201 to 300 mts')
    strike_off = fields.Monetary('Strike Off Price')