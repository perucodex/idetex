from odoo import fields, models

class ProductSupplierinfo(models.Model):
    _inherit = 'product.supplierinfo'

    price = fields.Float(digits='Product Price Custom Purchase')
