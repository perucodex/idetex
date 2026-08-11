# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.fields import Command
from odoo.exceptions import UserError

class MrpProduction(models.Model):
    _inherit = 'mrp.production'

    batch_id = fields.Many2one('mrp.workorder.batch', string='Batch')
    roll_ids = fields.One2many('mrp.production.roll', 'production_id', string='Rolls')
    production_type = fields.Selection([
        ('sale', 'Sale'),
        ('service', 'Service'),
        ('pilot', 'Pilot'),
        ('sample', 'Sample'),
        ('reposicion', 'Reposición'),
    ], string='Production Type', required=True, default='sale')

    @api.depends('bom_id', 'product_id', 'qty_producing', 'product_uom_id', 'never_product_template_attribute_value_ids')
    def _compute_workorder_ids(self):
        res = super()._compute_workorder_ids()
        for rec in self:
            for wo in rec.workorder_ids:
                # Solo sincronizar desde la operación de LdM cuando existe:
                # este compute se re-ejecuta ante muchos cambios (p.ej.
                # qty_producing) y pisar mrwo_id con False borraba la
                # Operación LAB de las OTs sin operación de LdM enlazada.
                op = wo.operation_id.operation_id
                if op and wo.mrwo_id != op:
                    wo.mrwo_id = op
        return res

    def _roll_done_qty(self, final=False):
        self.ensure_one()
        total_done = 0.0
        if final:
            wo_rolls = self.roll_ids
        else:
            wo_rolls = self.workorder_ids.mapped('roll_ids')
        for roll in wo_rolls:
            weight = float(roll.gross_weight or 0.0)
            if weight > 0:
                total_done += weight
                continue
            qty = float(roll.quantity or 0.0)
            if qty > 0:
                total_done += qty
        return total_done

    def _roll_qty_sync_targets(self):
        """Punto de extensión para definir dónde aplica la sincronización por rollos."""
        # El comportamiento por defecto aplica al recordset actual.
        # Los módulos dependientes pueden sobrescribir para filtrar objetivos (p. ej. solo tejido).
        return self

    def _sync_qty_producing_from_production_rolls(self):
        for production in self._roll_qty_sync_targets():
            # qty_producing debe provenir solo de los rollos finalizados.
            production.qty_producing = production._roll_done_qty(True)

    def button_mark_done(self):
        targets = self._roll_qty_sync_targets()
        for production in targets:
            if not production.roll_ids:
                continue

            # Rollos PESADOS en "Pesado de rollos": su quant ya se creó al
            # pesar (modo inventario). Volver a producir duplicaría el stock.
            weighed = production.roll_ids.filtered('weighed_date')
            if weighed:
                raise UserError(_(
                    'La OF %(prod)s tiene rollos pesados en "Pesado de rollos" '
                    '(su stock ya se generó al pesar): no se puede volver a '
                    'producir. Rollos: %(rolls)s',
                    prod=production.name,
                    rolls=', '.join(weighed.mapped('lot_id.name'))))

            # En tejido, el qty_produced de la orden de trabajo puede representar
            # tela intermedia (no rollos finales empacados). Se reinicia para que
            # el cierre final de la MO use solo lotes de rollos.
            # El core prohíbe cambiar qty_produced en workorders done/cancel.
            wo_to_reset = production.workorder_ids.filtered(lambda wo: wo.state not in ('done', 'cancel'))
            if wo_to_reset:
                wo_to_reset.write({'qty_produced': 0.0})
            if production.qty_produced:
                production.qty_produced = 0.0
            roll_lot_ids = production.roll_ids.mapped('lot_id').ids
            # Restricción del core: para productos con tracking por lote,
            # solo se permite un lot_producing_id.
            # Los lotes por rollo se conservan en líneas del movimiento final;
            # aquí se define un único lote principal.
            if production.product_tracking == 'lot':
                production.lot_producing_ids = [Command.set(roll_lot_ids[:1])]
            else:
                production.lot_producing_ids = [Command.set(roll_lot_ids)]

            missing_lot_rolls = production.roll_ids.filtered(lambda r: not r.lot_id)
            if missing_lot_rolls:
                raise UserError(_("All finished rolls must have a lot before producing."))

            total_qty = production._roll_done_qty(final=True)
            if total_qty <= 0:
                raise UserError(_("Finished roll quantity must be greater than zero before producing."))

            open_finished_moves = production.move_finished_ids.filtered(
                lambda m: m.product_id == production.product_id and m.state not in ('done', 'cancel')
            )
            finished_move = open_finished_moves[:1]
            if not finished_move:
                # Reconstruye movimientos finales faltantes (puede ocurrir tras cancelaciones/ediciones previas).
                production._create_update_move_finished()
                open_finished_moves = production.move_finished_ids.filtered(
                    lambda m: m.product_id == production.product_id and m.state not in ('done', 'cancel')
                )
                finished_move = open_finished_moves[:1]
            if not finished_move:
                # Último fallback: crear un movimiento final nuevo para el producto principal.
                move_vals = production._get_move_finished_values(
                    production.product_id.id,
                    total_qty,
                    production.product_uom_id.id,
                )
                finished_move = self.env['stock.move'].create(move_vals)
                if finished_move.state == 'draft':
                    finished_move._action_confirm()
            if not finished_move:
                raise UserError(_("No active finished move found for %(mo)s.", mo=production.display_name))

            # Mantener solo un movimiento final activo del producto principal.
            # Movimientos abiertos extra generan lotes/cantidades duplicadas en _post_inventory.
            extra_open_moves = (production.move_finished_ids.filtered(
                lambda m: m.product_id == production.product_id and m.state not in ('done', 'cancel')
            ) - finished_move)
            if extra_open_moves:
                extra_open_moves.with_context(skip_mo_check=True)._action_cancel()

            line_commands = [Command.clear()]
            for roll in production.roll_ids:
                roll_qty = float(roll.gross_weight or 0.0) or float(roll.quantity or 0.0)
                if roll_qty <= 0:
                    continue
                vals = finished_move._prepare_move_line_vals(quantity=roll_qty)
                vals.update({
                    'lot_id': roll.lot_id.id,
                    'quantity': roll_qty,
                    'picked': True,
                })
                line_commands.append(Command.create(vals))

            if len(line_commands) == 1:
                raise UserError(_("Finished rolls must have a positive quantity/weight to create lot moves."))

            finished_move.move_line_ids = line_commands
            # Mantener qty_produced en 0 antes de _post_inventory; el core marcará
            # picked y publicará este movimiento con el total de rollos.
            finished_move.picked = False
            finished_move.quantity = total_qty
            finished_move.product_uom_qty = total_qty
            production.qty_producing = total_qty
            production.qty_produced = 0.0

        ctx = dict(self.env.context, skip_consumption=True)
        return super(MrpProduction, self.with_context(ctx)).button_mark_done()

    def action_confirm(self):
        res = super().action_confirm()
        self.picking_ids.action_assign()
        return res