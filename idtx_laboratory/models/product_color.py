from odoo import models, fields, api, _

class ProductColor(models.Model):
    _name = 'product.color'
    _description = 'Product Color'

    name = fields.Char('Name')
    # color = fields.Integer('Color')