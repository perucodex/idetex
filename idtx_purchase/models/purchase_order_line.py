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

    def format_num_custom(self, value):
        """ Formats a float value stripping trailing zeros and the decimal point if it's an integer. """
        if not value:
            return "0"
        # Use Odoo's built-in float formatter to get thousands separators and current lang settings
        formatted = self.env['ir.qweb.fields'].get_formatter('float')(value, {'precision': 4, 'use_thousand': True})
        
        # Get the decimal point for the current language
        lang_code = self.env.context.get('lang') or self.env.user.lang or 'en_US'
        lang = self.env['res.lang']._lang_get(lang_code)
        decimal_point = lang.decimal_point
        
        if decimal_point in formatted:
            formatted = formatted.rstrip('0').rstrip(decimal_point)
        return formatted