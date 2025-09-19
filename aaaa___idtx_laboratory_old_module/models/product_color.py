from odoo import models, fields, api, _

class ProductColor(models.Model):
    _name = 'product.color'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Product Color'

    name = fields.Char('Name', tracking=True)
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
        index=True,
        required=True
    )