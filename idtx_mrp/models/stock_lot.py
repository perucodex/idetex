from odoo import fields, models, api

class StockLot(models.Model):
    _inherit = 'stock.lot'

    roll_id = fields.Many2one('mrp.production.roll', string='Roll')