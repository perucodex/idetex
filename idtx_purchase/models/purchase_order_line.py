from odoo import api, fields, models, _

class PurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'

    # Cambiamos los digito solo para compras
    price_unit = fields.Float(digits='Product Price Custom Purchase')
    price_unit_discounted = fields.Float(digits='Product Price Custom Purchase')

    product_qty = fields.Float(digits='Product Quantity Custom Purchase')
    qty_received = fields.Float(digits='Product Quantity Custom Purchase')
    qty_invoiced = fields.Float(digits='Product Quantity Custom Purchase')
    qty_to_invoice = fields.Float(digits='Product Quantity Custom Purchase')
    qty_received_manual = fields.Float(digits='Product Quantity Custom Purchase')
    qty_received_at_date = fields.Float(digits='Product Quantity Custom Purchase')
    qty_invoiced_at_date = fields.Float(digits='Product Quantity Custom Purchase')
    product_uom_qty = fields.Float(digits='Product Quantity Custom Purchase')