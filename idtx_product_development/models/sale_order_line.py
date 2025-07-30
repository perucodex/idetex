from odoo import models, fields, api, _
from odoo.exceptions import UserError

class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    is_weaving = fields.Boolean(related='product_template_id.is_weaving', store=True)