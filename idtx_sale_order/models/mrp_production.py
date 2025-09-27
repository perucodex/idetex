# -*- coding: utf-8 -*-

from odoo import fields, models

class MrpProduction(models.Model):
    _inherit = 'mrp.production'

    sale_order_line_id = fields.Many2one('sale.order.line', string='Sale Order Line')
    color_recipe_id = fields.Many2one('color.recipe', string='Color Recipe', compute='_compute_color_recipe')

    def _compute_color_recipe(self):
        for rec in self:
            if rec.sale_order_line_id:
                rec.color_recipe_id = rec.sale_order_line_id.lab_dev_id.lab_dev_line_ids.filtered(lambda l: l.sale_order_line_id == rec.sale_order_line_id).color_recipe_ids.filtered(lambda l: l.state == 'approved')
            else:
                rec.color_recipe_id = False