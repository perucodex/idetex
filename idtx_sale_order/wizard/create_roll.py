from odoo import fields, models, _

class CreateRoll(models.TransientModel):
    _name = 'create.roll'

    sale_order_id = fields.Many2one('sale.order', string='Sale Order')