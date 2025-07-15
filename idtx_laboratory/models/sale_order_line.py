from odoo import models, fields

class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    product_color_id = fields.Many2one('product.color', string='Color')
    lab_dev_id = fields.Many2one('lab.dev', string='Lab Dev')