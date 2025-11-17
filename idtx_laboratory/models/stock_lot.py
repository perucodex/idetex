from odoo import fields, models

class StockLot(models.Model):
    _inherit = 'stock.lot'

    color_recipe_id = fields.Many2one('color.recipe', string='Color Recipe')
    color_code = fields.Char(related='color_recipe_id.color_code')
    color_name = fields.Char(related='color_recipe_id.color_name')