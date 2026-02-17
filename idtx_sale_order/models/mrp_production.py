# -*- coding: utf-8 -*-

from odoo import fields, models, api, _
from odoo.fields import Command
from odoo.exceptions import UserError

class MrpProduction(models.Model):
    _inherit = 'mrp.production'

    sale_order_line_id = fields.Many2one('sale.order.line', string='Sale Order Line', copy=True)
    order_id = fields.Many2one('sale.order', string='Sale Order', related='sale_order_line_id.order_id', store=True)
    need_recipe = fields.Boolean('Need Recipe', compute='_compute_need_recipe')
    color_recipe_id = fields.Many2one('color.recipe', string='Color Recipe', compute='_compute_color_recipe', store=True)
    color_code = fields.Char(related='color_recipe_id.color_code')
    color_name = fields.Char(related='color_recipe_id.color_name')
    manual_recipe = fields.Boolean('manual_recipe', default=False)
    manual_color_recipe_id = fields.Many2one('color.recipe', string='Manual Color Recipe', ondelete='restrict')

    @api.onchange('color_recipe_id')
    def _onchange_color_recipe_id(self):
        for production in self:
            list_move_raw = [Command.link(move.id) for move in production.move_raw_ids.filtered(lambda m: not m.bom_line_id)]
            for line in production.color_recipe_id.color_recipe_process_ids.color_recipe_process_line_ids:
                if production.bom_id and production.product_id and production.product_qty > 0:
                    # keep manual entries
                    # TODO recalcular la formula de peso y litro para saber el consumo de productos quimicos
                    moves_raw_values = [production._get_move_raw_values(
                        line.product_id,
                        line.factor * production.product_qty,
                        line.product_id.uom_id,)]
                    move_raw_dict = {move.bom_line_id.id: move for move in production.move_raw_ids.filtered(lambda m: m.bom_line_id)}
                    for move_raw_values in moves_raw_values:
                        if move_raw_values['bom_line_id'] in move_raw_dict:
                            # update existing entries
                            list_move_raw += [Command.update(move_raw_dict[move_raw_values['bom_line_id']].id, move_raw_values)]
                        else:
                            # add new entries
                            list_move_raw += [Command.create(move_raw_values)]
                else:
                    production.move_raw_ids = [Command.delete(move.id) for move in production.move_raw_ids.filtered(lambda m: m.bom_line_id)]    
            production.move_raw_ids = list_move_raw

    def _compute_need_recipe(self):
        for rec in self:
            rec.need_recipe = True if rec.sale_order_line_id and rec.sale_order_line_id.lab_dev_line_id else False

    @api.depends('manual_color_recipe_id','sale_order_line_id')
    def _compute_color_recipe(self):
        for rec in self:
            if rec.manual_recipe:
                color_recipe_id = rec.manual_color_recipe_id
            else:
                if rec.sale_order_line_id:
                    color_recipe_id = rec.sale_order_line_id.lab_dev_line_id.color_recipe_ids.filtered(lambda l: l.state == 'approved')
                else:
                    color_recipe_id = False
            rec.color_recipe_id = color_recipe_id
            rec.manual_color_recipe_id = color_recipe_id

    def unlink(self):
        if self.env.context.get('delete_from_sale_order'):
            for production in self:
                if production.state not in ('draft','confirmed','cancel'):
                    raise UserError(_('Can\'t delete production in %s') %production.state)
        return super().unlink()

    def action_confirm(self):
        if self.need_recipe and not self.color_recipe_id:
            raise UserError(_('Production must have an approved recipe.'))
        return super().action_confirm()
    
    def action_manual(self):
        self.manual_recipe = not self.manual_recipe
        if not self.manual_recipe and self.sale_order_line_id.lab_dev_line_id.color_recipe_ids.filtered(lambda l: l.state == 'approved'):
            self.color_recipe_id = self.sale_order_line_id.lab_dev_line_id.color_recipe_ids.filtered(lambda l: l.state == 'approved')
