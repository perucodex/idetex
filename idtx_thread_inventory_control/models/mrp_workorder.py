# -*- coding: utf-8 -*-
"""Cierre del tejido: liquidación de las bolsas de hilo separadas para la OT."""

from odoo import _, fields, models
from odoo.exceptions import UserError


class MrpWorkorder(models.Model):
    _inherit = 'mrp.workorder'

    weaving_liquidation_ids = fields.One2many(
        'thread.weaving.liquidation', 'workorder_id', string='Liquidaciones de Hilo',
        readonly=True,
        help='Liquidaciones de hilo hechas al cerrar el tejido de esta orden.')
    weaving_liquidation_count = fields.Integer(
        compute='_compute_weaving_liquidation_count')

    weaving_liquidated_qty = fields.Float(
        'Tela ya liquidada (kg)', digits=(16, 2), copy=False, readonly=True,
        help='Kilos de tela que ya se liquidaron contra el hilo. Si la orden se '
             'reabre por reproceso, la siguiente liquidación solo considera lo '
             'tejido después.')

    def _compute_weaving_liquidation_count(self):
        datos = self.env['thread.weaving.liquidation']._read_group(
            [('workorder_id', 'in', self.ids)], ['workorder_id'], ['__count'])
        conteo = {wo.id: n for wo, n in datos}
        for wo in self:
            wo.weaving_liquidation_count = conteo.get(wo.id, 0)

    # ------------------------------------------------------------------
    # Bolsas de la orden de trabajo
    # ------------------------------------------------------------------
    def _weaving_thread_moves(self):
        """Movimientos de hilo de la OF, aún abiertos."""
        self.ensure_one()
        return self.production_id.move_raw_ids.filtered(
            lambda m: m.product_id.is_thread
            and m.state not in ('done', 'cancel'))

    def _weaving_reserved_bags(self):
        """Bolsas separadas (reservadas) para tejer esta OT."""
        self.ensure_one()
        return self._weaving_thread_moves().thread_bag_ids.filtered(
            lambda b: b.state == 'reserved')

    def action_open_weaving_close(self):
        """Abre la liquidación de hilo del tejido."""
        self.ensure_one()
        if self.operation_type != 'weaving':
            raise UserError(_('La liquidación de hilo es de la operación de tejido.'))
        if self.state in ('done', 'cancel'):
            raise UserError(_('La orden de trabajo ya está cerrada.'))
        if not self._weaving_reserved_bags():
            raise UserError(_(
                'No hay bolsas separadas para esta orden de trabajo: elige las '
                'bolsas en los componentes de la OF antes de liquidar.'))
        return self._action_weaving_close()

    def _action_weaving_close(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Cerrar tejido y liquidar hilo'),
            'res_model': 'thread.weaving.close.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_workorder_id': self.id},
        }

    def _needs_weaving_liquidation(self):
        """La OT de tejido no se puede cerrar sin liquidar el hilo separado."""
        self.ensure_one()
        return bool(
            self.operation_type == 'weaving'
            and self.state not in ('done', 'cancel')
            and not self.env.context.get('skip_weaving_liquidation')
            and self._weaving_reserved_bags()
        )

    def do_finish(self):
        """Cierre desde el Taller: primero la liquidación del hilo.

        El Taller abre la acción que devuelve este método, así que el tejedor ve
        la pantalla de liquidación al pulsar "Marcar como hecha" y la OT se
        cierra desde ahí (la propia pantalla vuelve a llamar a este método con
        `skip_weaving_liquidation`).
        """
        if len(self) == 1 and self._needs_weaving_liquidation():
            return self._action_weaving_close()
        return super().do_finish()

    def button_finish(self):
        """No se cierra una OT de tejido con hilo separado sin liquidarlo.

        Se avisa en vez de devolver la acción porque a este método se llega
        también desde recorridos que ignoran el valor devuelto (cierre de la OF,
        arrastrar la tarjeta en el Taller) y la OT se quedaría abierta sin que
        nadie se enterara.
        """
        pendientes = self.filtered(lambda wo: wo._needs_weaving_liquidation())
        if pendientes:
            raise UserError(_(
                'Falta liquidar el hilo del tejido de %(ots)s. Usa el botón '
                '"Cerrar tejido y liquidar hilo" para declarar las bolsas '
                'usadas, el hilo bajado de máquina y la merma.',
                ots=', '.join(pendientes.mapped('display_name'))))
        return super().button_finish()

    # ------------------------------------------------------------------
    # Movimientos de la liquidación
    # ------------------------------------------------------------------
    def _weaving_consume_bags(self, bags):
        """Consume COMPLETAS las bolsas abiertas en la tejedora.

        Devuelve los kilos consumidos. La cantidad del movimiento pasa a ser el
        peso de las bolsas usadas (no los kilos tejidos): lo que salió del
        almacén es la bolsa entera, y el reparto entre tela, 2da y merma se
        registra aparte.
        """
        self.ensure_one()
        if not bags:
            return 0.0
        MoveLine = self.env['stock.move.line']
        total = 0.0
        for move in self._weaving_thread_moves():
            bolsas_move = bags & move.thread_bag_ids
            if not bolsas_move:
                continue
            por_lote = {}
            for bag in bolsas_move:
                por_lote[bag.lot_id] = por_lote.get(bag.lot_id, 0.0) + bag.net_weight
            kg = sum(por_lote.values())
            if kg <= 0:
                continue
            # Se rehacen las líneas con el peso real de las bolsas usadas.
            move.move_line_ids.filtered(lambda ml: ml.state not in ('done', 'cancel')).unlink()
            for lote, cantidad in por_lote.items():
                vals = move._prepare_move_line_vals(quantity=0)
                vals.update({'lot_id': lote.id, 'quantity': cantidad})
                MoveLine.create(vals)
            # Las bolsas no usadas salen del movimiento antes de cerrarlo, así
            # `_action_done` no las marca consumidas.
            move.thread_bag_ids = [(6, 0, bolsas_move.ids)]
            move.product_uom_qty = kg
            move.picked = True
            move._action_done()
            total += kg
        return total

    def _weaving_release_bags(self, bags):
        """Suelta la reserva de las bolsas que no se abrieron: vuelven a
        Disponible en su ubicación, sin ningún movimiento de stock."""
        self.ensure_one()
        if not bags:
            return
        for move in self.production_id.move_raw_ids.filtered(
                lambda m: m.product_id.is_thread):
            restantes = move.thread_bag_ids - bags
            if len(restantes) != len(move.thread_bag_ids):
                move.thread_bag_ids = [(6, 0, restantes.ids)]
            # Un movimiento que se queda sin bolsas es hilo que no se usó: se
            # suelta su reserva y se cancela, si no seguiría reservando stock
            # de un lote que nadie tocó.
            if not move.thread_bag_ids and move.state not in ('done', 'cancel'):
                move._do_unreserve()
                move._action_cancel()
        bags.write({
            'state': 'available',
            'consumed_move_line_id': False,
            'production_id': False,
        })
