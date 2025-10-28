from odoo import api, fields, models, _

class PurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'

    # Cambiamos los digito solo para compras
    price_unit = fields.Float(digits='Product Price Custom Purchase')
    price_unit_discounted = fields.Float(digits='Product Price Custom Purchase')