from odoo import models, fields, api, _

class ProductTitle(models.Model):
    _inherit = 'product.title'

    currency_id = fields.Many2one('res.currency', string='Currency', default=lambda self: self.env.ref('base.USD'))
    unit_price = fields.Monetary('Unit Price', currency_field='currency_id')