from odoo import models, fields, api, _

class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    product_color_id = fields.Many2one('product.color', string='Color')

