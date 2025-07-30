from odoo import models, fields, api, _

class ProductColor(models.Model):
    _name = 'product.color'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Product Color'

    name = fields.Char('Name', tracking=True)
    # currency_id = fields.Many2one('res.currency', string='Currency')
    # unit_price = fields.Monetary('Unit Price', currency_field='currency_id')
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
        index=True,
        required=True
    )