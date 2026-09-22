# -*- coding: utf-8 -*-

from odoo import fields, models, api, _
from odoo.fields import Command
from odoo.exceptions import UserError, AccessError

PRODUCT_DEV_MANAGER_GROUP = 'idtx_product_development.group_module_product_development_manager'

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
        # La línea guarda fases del MAESTRO (ruta del análisis): se comparan
        # con la fase maestra de cada operación de la LdM (operation_id).
        for production in self:
            line = production.sale_order_line_id
            if not line or production.state != 'draft':
                continue
            excluded = line.available_operation_ids - line.operation_ids
            if not excluded:
                continue
            to_delete = production.workorder_ids.filtered(
                lambda wo: wo.operation_id.operation_id in excluded)
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

    # ------------------------------------------------------------------
    # OF con pedido: convertir en PILOTO / revertir al tipo del pedido
    # (solo Desarrollo de Producto / Administrador; JP, 21-sep-2026)
    # ------------------------------------------------------------------
    def _check_production_type_manager(self):
        if not self.env.user.has_group(PRODUCT_DEV_MANAGER_GROUP):
            raise AccessError(_(
                'Solo el administrador de Desarrollo de Producto puede cambiar el '
                'tipo de producción de una OF con pedido de venta.'))

    def _check_production_type_switchable(self):
        for rec in self:
            if not rec.order_id:
                raise UserError(_(
                    'Solo aplica a OF creadas desde un pedido de venta (%s no tiene pedido).', rec.name))
            if rec.state in ('done', 'cancel'):
                raise UserError(_(
                    'La OF %s ya está terminada o cancelada: no se puede cambiar su tipo.', rec.name))

    def _set_production_type_logged(self, new_type):
        self.ensure_one()
        labels = dict(self._fields['production_type']._description_selection(self.env))
        old_type = self.production_type
        if old_type == new_type:
            return
        # La restricción de mrp.production (muestra/piloto no permitidos con el
        # producto en producción) valida el cambio.
        self.production_type = new_type
        self.message_post(body=_(
            'Tipo de producción cambiado de %(old)s a %(new)s por %(user)s.',
            old=labels.get(old_type, old_type), new=labels.get(new_type, new_type),
            user=self.env.user.name))

    def action_set_pilot_production_type(self):
        """La primera OF de un producto nuevo (venta o servicio) se fabrica como
        PILOTO: se puede confirmar sin piloto previo y, al terminar, el
        producto queda en estado Piloto."""
        self._check_production_type_manager()
        self._check_production_type_switchable()
        for rec in self:
            rec._set_production_type_logged('pilot')

    def action_revert_production_type(self):
        """Vuelve al tipo que viene del pedido de venta (venta o servicio)."""
        self._check_production_type_manager()
        self._check_production_type_switchable()
        for rec in self:
            rec._set_production_type_logged(rec.order_id.sale_type)

    def _compute_need_recipe(self):
        for rec in self:
            # Solo exige receta si viene de venta CON color de laboratorio.
            # (El flujo de receta manual se retiró: la receta real la resuelve
            # la PARTIDA por combinación de productos + lotes; la OF solo
            # muestra color y código.)
            rec.need_recipe = bool(rec.sale_order_line_id and rec.sale_order_line_id.lab_dev_line_id)

    @api.depends('color_recipe_id.lab_dev_line_id.color_code', 'color_recipe_id.lab_dev_line_id.color_name',
                 'manual_lab_dev_line_id.color_code', 'manual_lab_dev_line_id.color_name',
                 'sale_order_line_id.lab_dev_line_id.color_code', 'sale_order_line_id.lab_dev_line_id.color_name')
    def _compute_color_labels(self):
        # Color de la receta; si la OF libre solo tiene color elegido (sin
        # receta aun), se muestra ese color. Sin receta de producción todavía,
        # el color es el de la línea del pedido (la OF ya puede confirmarse
        # solo con el color de desarrollo aprobado).
        for rec in self:
            line = (rec.color_recipe_id.lab_dev_line_id or rec.manual_lab_dev_line_id
                    or rec.sale_order_line_id.lab_dev_line_id)
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
        # JP (18-sep-2026): para confirmar la OF basta el color de DESARROLLO
        # aprobado (línea de Lab Dip del pedido). La receta de PRODUCCIÓN no
        # se exige aquí: la resuelve y valida la PARTIDA al armarla/teñir
        # (recipe_lot_warning y el registro de TEÑIDO del Taller).
        for rec in self:
            if not rec.need_recipe:
                continue
            line = rec.sale_order_line_id.lab_dev_line_id
            if line.state != 'approved':
                raise UserError(_(
                    'No se puede confirmar %(prod)s: el color %(color)s del pedido '
                    'aún no está aprobado en laboratorio (Lab Dip %(ld)s).',
                    prod=rec.name, color=line.display_name,
                    ld=line.lab_dev_id.name or ''))
        return super().action_confirm()
    
    def action_manual(self):
        self.manual_recipe = not self.manual_recipe
        if not self.manual_recipe:
            approved = self.sale_order_line_id.lab_dev_line_id.color_recipe_ids.filtered(
                lambda l: l.state == 'approved' and self.product_tmpl_id in l.product_ids)
            if approved:
                self.color_recipe_id = approved[:1]