# -*- coding: utf-8 -*-
"""Cierre del tejido: rearmar las bolsas con el hilo que volvió de la máquina."""

from odoo import _, models
from odoo.exceptions import UserError


class MrpWorkorder(models.Model):
    _inherit = 'mrp.workorder'

    def _weaving_thread_moves(self):
        """Componentes de hilo de la OF, aún abiertos."""
        self.ensure_one()
        return self.production_id.move_raw_ids.filtered(
            lambda m: m.product_id.product_tmpl_id.is_thread
            and m.state not in ('done', 'cancel'))

    def _weaving_reserved_bags(self):
        """Bolsas separadas para tejer esta OT.

        Son las bolsas enlazadas al componente que todavía no se consumieron:
        las que se abrieron en la máquina. No se filtra por estado 'reserved'
        porque una bolsa puede quedar 'available' si su reserva se soltó por
        fuera, y sigue siendo parte de la selección del componente.
        """
        self.ensure_one()
        return self._weaving_thread_moves().thread_bag_ids.filtered(
            lambda b: b.state != 'consumed')

    def _weaving_consume_bags(self, bags):
        """Consume COMPLETAS las bolsas que se abrieron en la máquina.

        La cantidad del movimiento pasa a ser el peso de esas bolsas, no los
        kilos tejidos: del almacén salió la bolsa entera. Lo que volvió como
        bolsas nuevas entra aparte, y la diferencia es la tela más la pérdida.
        Sin esto el core deja el consumo en proporción a lo producido y el hilo
        rearmado aparecería de la nada.
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
            move.move_line_ids.filtered(
                lambda ml: ml.state not in ('done', 'cancel')).unlink()
            for lote, cantidad in por_lote.items():
                vals = move._prepare_move_line_vals(quantity=0)
                vals.update({'lot_id': lote.id, 'quantity': cantidad})
                MoveLine.create(vals)
            move.thread_bag_ids = [(6, 0, bolsas_move.ids)]
            move.product_uom_qty = kg
            move.picked = True
            move._action_done()
            total += kg
        return total

    def _action_weaving_close_bags(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Cerrar tejido y rearmar bolsas'),
            'res_model': 'thread.weaving.close.bags.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_workorder_id': self.id},
        }

    def action_open_weaving_close_bags(self):
        """Abre el rearmado de bolsas del cierre de tejido."""
        self.ensure_one()
        if self.operation_type != 'weaving':
            raise UserError(_('El rearmado de bolsas es de la operación de tejido.'))
        if self.state in ('done', 'cancel'):
            raise UserError(_('La orden de trabajo ya está cerrada.'))
        if not self._weaving_reserved_bags():
            raise UserError(_(
                'No hay bolsas separadas para esta orden de trabajo: elige las '
                'bolsas en los componentes de la OF antes de cerrar.'))
        return self._action_weaving_close_bags()

    def _needs_weaving_close_bags(self):
        """Con bolsas separadas, el cierre pasa por el rearmado."""
        self.ensure_one()
        return bool(
            self.operation_type == 'weaving'
            and self.state not in ('done', 'cancel')
            and not self.env.context.get('skip_weaving_close_bags')
            and self._weaving_reserved_bags()
        )

    def do_finish(self):
        """Cierre desde el Taller: primero se rearman las bolsas.

        El Taller ejecuta la acción que devuelve este método, así que el tejedor
        ve la pantalla al pulsar "Marcar como hecha"; la propia pantalla vuelve a
        llamar al cierre con `skip_weaving_close_bags`.
        """
        if len(self) == 1 and self._needs_weaving_close_bags():
            return self._action_weaving_close_bags()
        return super().do_finish()

    def button_finish(self):
        """No se cierra el tejido sin decir qué pasó con las bolsas.

        Se avisa en vez de devolver la acción porque a este método se llega
        también desde recorridos que ignoran el valor devuelto (cierre de la OF,
        arrastrar la tarjeta en el Taller) y la OT quedaría abierta en silencio.
        """
        pendientes = self.filtered(lambda wo: wo._needs_weaving_close_bags())
        if pendientes:
            raise UserError(_(
                'Falta rearmar las bolsas del tejido de %(ots)s. Usa el botón '
                '"Cerrar tejido y rearmar bolsas" para registrar las bolsas que '
                'se armaron con el hilo bajado de máquina.',
                ots=', '.join(pendientes.mapped('display_name'))))
        return super().button_finish()
