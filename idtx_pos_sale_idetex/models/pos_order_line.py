# -*- coding: utf-8 -*-
from odoo import models, fields, api

class PosOrderLine(models.Model):
    _inherit = 'pos.order.line'

    color_name = fields.Char(string='Color Name', help='Nombre del color del rollo seleccionado')

    @api.model
    def _load_pos_data_fields(self, config):
        params = super()._load_pos_data_fields(config)
        params += ['color_name']
        return params

    # ===== HOOKS DE RESERVA: cubre el caso de eliminar/modificar líneas directamente =====
    # Si se quita una línea de un pedido guardado, el lot asociado debe liberarse.

    @api.model_create_multi
    def create(self, vals_list):
        """ Al crear líneas, re-sincronizar reservas del pedido padre. """
        lines = super().create(vals_list)                                       # crear normalmente
        lines.mapped('order_id')._idtx_sync_lot_reservations()                  # sincronizar
        return lines

    def write(self, vals):
        """ Al cambiar pack_lot_ids u otros campos relevantes, re-sincronizar. """
        res = super().write(vals)                                               # escribir normalmente
        if 'pack_lot_ids' in vals:                                              # solo si cambiaron los lotes
            self.mapped('order_id')._idtx_sync_lot_reservations()
        return res

    def unlink(self):
        """ Al eliminar línea, liberar los lots de esa línea si estaban reservados. """
        orders = self.mapped('order_id')                                        # capturar antes del unlink
        res = super().unlink()                                                  # eliminar primero
        orders._idtx_sync_lot_reservations()                                    # luego sincronizar
        return res
