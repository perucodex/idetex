# -*- coding: utf-8 -*-

from odoo import fields, models, api, _
from odoo.exceptions import UserError

class MrpProduction(models.Model):
    _inherit = 'mrp.production'

    sale_order_line_id = fields.Many2one('sale.order.line', string='Sale Order Line')
    color_recipe_id = fields.Many2one('color.recipe', string='Color Recipe', compute='_compute_color_recipe')
    manual_recipe = fields.Boolean('manual_recipe', default=False)
    manual_color_recipe_id = fields.Many2one('color.recipe', string='Manual Color Recipe', ondelete='restrict')

    @api.depends('manual_color_recipe_id','sale_order_line_id')
    def _compute_color_recipe(self):
        for rec in self:
            if rec.manual_recipe:
                color_recipe_id = rec.manual_color_recipe_id
            else:
                if rec.sale_order_line_id:
                    # color_recipe_id = rec.sale_order_line_id.lab_dev_ids.lab_dev_line_ids.filtered(lambda l: l.sale_order_line_id == rec.sale_order_line_id).color_recipe_ids.filtered(lambda l: l.state == 'approved')
                    color_recipe_id = rec.sale_order_line_id.lab_dev_line_id.color_recipe_ids.filtered(lambda l: l.state == 'approved')
                else:
                    color_recipe_id = False
            rec.color_recipe_id = color_recipe_id
            rec.manual_color_recipe_id = color_recipe_id

    def unlink(self):
        if self.env.context.get('delete_from_sale_order'):
            for production in self:
                if production.state not in ('draft','confirmed'):
                    raise UserError(_('Can\'t delete production in %s') %production.state)
        return super().unlink()

    # def action_confirm(self):
    #     if not self.color_recipe_id:
    #         raise UserError(_('Production must have a recipe.'))
    #     return super().color_recipe_id()
    
    def action_manual(self):
        self.manual_recipe = not self.manual_recipe