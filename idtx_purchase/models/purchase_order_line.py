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
        
        # Use the float field converter from Odoo's QWeb fields
        # Note: In Odoo 19, the model is 'ir.qweb.field.float'
        formatted = self.env['ir.qweb.field.float'].value_to_html(value, {'precision': 4})
        
        # Ensure we have a string to perform rstrip
        formatted = str(formatted)
        
        # Get the decimal point for the current language to safely strip zeros
        lang_code = self.env.context.get('lang') or self.env.user.lang or 'en_US'
        lang = self.env['res.lang']._lang_get(lang_code)
        decimal_point = lang.decimal_point
        
        if decimal_point in formatted:
            # We only strip zeros after the decimal point
            # If the number is something like '4,000.0000', it becomes '4,000'
            # If it's '25.0500', it becomes '25.05'
            parts = formatted.split(decimal_point)
            if len(parts) == 2:
                fractional = parts[1].rstrip('0')
                if fractional:
                    formatted = parts[0] + decimal_point + fractional
                else:
                    formatted = parts[0]
        return formatted