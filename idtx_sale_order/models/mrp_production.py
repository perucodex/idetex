# -*- coding: utf-8 -*-

from odoo import fields, models, api, _
from odoo.fields import Command
from odoo.exceptions import UserError

class MrpProduction(models.Model):
    _inherit = 'mrp.production'

    sale_order_line_id = fields.Many2one('sale.order.line', string='Sale Order Line', copy=True)
    order_id = fields.Many2one('sale.order', string='Sale Order', related='sale_order_line_id.order_id', store=True)
    partner_id = fields.Many2one('res.partner', string='Client', related='order_id.partner_id', store=True)
    need_recipe = fields.Boolean('Need Recipe', compute='_compute_need_recipe')
    color_recipe_id = fields.Many2one('color.recipe', string='Color Recipe', compute='_compute_color_recipe', store=True)
    color_code = fields.Char(compute='_compute_color_labels')
    color_name = fields.Char(compute='_compute_color_labels')
    manual_recipe = fields.Boolean('manual_recipe', default=False)
    manual_color_recipe_id = fields.Many2one('color.recipe', string='Manual Color Recipe', ondelete='restrict')
    # OF LIBRE (sin pedido de venta: muestra, piloto, reposicion interna):
    # el usuario elige el color a mano (solo en borrador) y la receta se
    # resuelve sola (_manual_recipe_for_line), como en una OF con pedido.
    manual_lab_dev_line_id = fields.Many2one(
        'lab.dev.line', string='Color', ondelete='restrict',
        help='Color elegido a mano en una OF sin pedido de venta (muestra, '
             'piloto). Define la receta de color de la OF y, con ella, la de '
             'la partida en la que se tiñan sus rollos.')

    @api.depends('sale_order_line_id', 'sale_order_line_id.operation_ids')
    def _compute_workorder_ids(self):
        res = super()._compute_workorder_ids()
        # La OF debe respetar las operaciones elegidas en la línea de venta:
        # el vendedor puede QUITAR operaciones con precio (p.ej. servicio sin
        # tejido) y esas no deben generar orden de trabajo. Solo se filtran
        # las que estaban disponibles para elegir (available_operation_ids);
        # las auxiliares sin precio (control de peso/calidad, etc.) no son
        # seleccionables en la línea y se conservan siempre.
        for production in self:
            line = production.sale_order_line_id
            if not line or production.state != 'draft':
                continue
            excluded = line.available_operation_ids - line.operation_ids
            if not excluded:
                continue
            to_delete = production.workorder_ids.filtered(
                lambda wo: wo.operation_id in excluded)
            if to_delete:
                production.workorder_ids = [Command.delete(wo.id) for wo in to_delete]
        return res

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
            # Solo exige receta si viene de venta CON color de laboratorio.
            # (El flujo de receta manual se retiró: la receta real la resuelve
            # la PARTIDA por combinación de productos + lotes; la OF solo
            # muestra color y código.)
            rec.need_recipe = bool(rec.sale_order_line_id and rec.sale_order_line_id.lab_dev_line_id)

    @api.depends('color_recipe_id.lab_dev_line_id.color_code', 'color_recipe_id.lab_dev_line_id.color_name',
                 'manual_lab_dev_line_id.color_code', 'manual_lab_dev_line_id.color_name')
    def _compute_color_labels(self):
        # Color de la receta; si la OF libre solo tiene color elegido (sin
        # receta aun), se muestra ese color.
        for rec in self:
            line = rec.color_recipe_id.lab_dev_line_id or rec.manual_lab_dev_line_id
            rec.color_code = line.color_code
            rec.color_name = line.color_name

    def _manual_recipe_for_line(self, line):
        """Receta de una OF libre a partir del color elegido (misma regla que
        con pedido): aprobada que incluye el producto, la unitaria exacta
        primero y luego la combinada mas chica. El producto de una muestra
        normalmente no figura en ninguna receta: entonces la unica aprobada
        del color y, si hay varias, la mas reciente (el laboratorio ajusta
        la sub-receta en la partida)."""
        self.ensure_one()
        approved = line.color_recipe_ids.filtered(lambda r: r.state == 'approved')
        match = approved.filtered(lambda r: self.product_tmpl_id in r.product_ids)
        if match:
            exact = match.filtered(lambda r: len(r.product_ids) == 1)
            return (exact or match.sorted(key=lambda r: (len(r.product_ids), r.id)))[:1]
        return approved.sorted(key=lambda r: r.id, reverse=True)[:1]

    @api.depends('manual_recipe', 'manual_color_recipe_id', 'manual_lab_dev_line_id', 'product_tmpl_id', 'sale_order_line_id', 'sale_order_line_id.lab_dev_line_id', 'sale_order_line_id.lab_dev_line_id.color_recipe_ids.state', 'sale_order_line_id.lab_dev_line_id.color_recipe_ids.product_ids')
    def _compute_color_recipe(self):
        for rec in self:
            if rec.manual_recipe or not rec.sale_order_line_id:
                # Receta manual (o OF libre sin pedido): manda lo elegido.
                color_recipe_id = rec.manual_color_recipe_id
                line = rec.manual_lab_dev_line_id
                if line and (not color_recipe_id or color_recipe_id.lab_dev_line_id != line):
                    # Cambio de color: la receta anterior ya no aplica.
                    color_recipe_id = rec._manual_recipe_for_line(line)
                elif color_recipe_id and not line:
                    rec.manual_lab_dev_line_id = color_recipe_id.lab_dev_line_id
            else:
                if rec.sale_order_line_id:
                    # La línea de lab dev tiene recetas aprobadas por producto
                    # o por COMBINACIÓN (teñidos juntos). Pueden coexistir
                    # (JERSEY y JERSEY+RIB): la OF prefiere la receta UNITARIA
                    # exacta de su producto; si no existe, la combinada que lo
                    # contenga (la de menos productos, determinista).
                    candidates = rec.sale_order_line_id.lab_dev_line_id.color_recipe_ids.filtered(
                        lambda l: l.state == 'approved' and rec.product_tmpl_id in l.product_ids)
                    exact = candidates.filtered(lambda l: len(l.product_ids) == 1)
                    color_recipe_id = (exact or candidates.sorted(
                        key=lambda l: (len(l.product_ids), l.id)))[:1]
                else:
                    color_recipe_id = False
            rec.color_recipe_id = color_recipe_id
            rec.manual_color_recipe_id = color_recipe_id

    # def unlink(self):
    #     if self.env.context.get('delete_from_sale_order'):
    #         for production in self:
    #             if production.state not in ('draft','confirmed','cancel'):
    #                 raise UserError(_('Can\'t delete production in %s') %production.state)
    #     return super().unlink()

    def action_confirm(self):
        if self.need_recipe and not self.color_recipe_id:
            raise UserError(_('Production must have an approved recipe.'))
        return super().action_confirm()
    
    def action_manual(self):
        self.manual_recipe = not self.manual_recipe
        if not self.manual_recipe:
            approved = self.sale_order_line_id.lab_dev_line_id.color_recipe_ids.filtered(
                lambda l: l.state == 'approved' and self.product_tmpl_id in l.product_ids)
            if approved:
                self.color_recipe_id = approved[:1]