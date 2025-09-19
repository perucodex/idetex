from odoo import models, fields

class ProductColor(models.Model):
    _name = 'product.color'
    _description = 'Product Color'

    name = fields.Char('Name')
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
        index=True,
        required=True
    )