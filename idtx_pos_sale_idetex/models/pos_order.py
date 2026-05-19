# -*- coding: utf-8 -*-
from odoo import models, api, _
import re

# Estados de pos.order en los que NO debe haber reserva activa:
# - 'paid'/'done'/'invoiced': el stock saldrá por movimiento de inventario al validar
# - 'cancel': la orden quedó descartada
_POS_ORDER_RELEASED_STATES = ('paid', 'done', 'invoiced', 'cancel')

class PosOrder(models.Model):
    _inherit = 'pos.order'

    # ===== LÓGICA DE RESERVA DE ROLLOS =====
    # Cuando un pedido se guarda con clickSaveOrder (state='draft'), todos los lots
    # referenciados en sus líneas quedan bloqueados (pos_reserved_order_id = self.id).
    # Al pagar, cancelar o eliminar la orden, los lots se liberan automáticamente.

    def _idtx_get_order_lot_ids(self):
        """
        Devuelve el recordset de stock.lot referenciados por las líneas de la orden.
        Nota: pos.pack.operation.lot solo guarda lot_name (string), NO un Many2one a stock.lot.
        Por eso resolvemos cada lote buscando por nombre + producto de la línea.
        """
        self.ensure_one()                                                       # una orden por llamada
        StockLot = self.env['stock.lot']
        result = StockLot.browse()                                              # recordset vacío inicial
        for line in self.lines:
            product = line.product_id                                           # producto de la línea
            for pack_lot in line.pack_lot_ids:                                  # cada pos.pack.operation.lot
                if not pack_lot.lot_name:
                    continue                                                    # ignorar entradas vacías
                # Buscar el stock.lot real por nombre + producto (lot_name no es globalmente único)
                lot = StockLot.search([
                    ('name', '=', pack_lot.lot_name),
                    ('product_id', '=', product.id),
                ], limit=1)
                if lot:
                    result |= lot                                               # acumular en el recordset
        return result

    def _idtx_sync_lot_reservations(self):
        """
        Sincroniza el campo pos_reserved_order_id de los lots según el estado actual de la orden.
        - Si state = draft → reserva todos los lots de las líneas
        - Si state != draft → libera todos los lots que tenía reservados
        - Si se quitaron líneas → libera los lots que ya no están en la orden
        """
        StockLot = self.env['stock.lot']                                        # alias corto al modelo
        for order in self:
            # Lots actualmente referenciados en las líneas de esta orden
            current_lots = order._idtx_get_order_lot_ids()
            # Lots que ESTABAN reservados por esta orden en la base
            previously_reserved = StockLot.search([('pos_reserved_order_id', '=', order.id)])

            if order.state in _POS_ORDER_RELEASED_STATES:
                # Orden pagada/cancelada → liberar TODO lo que tenía reservado
                if previously_reserved:
                    previously_reserved.write({'pos_reserved_order_id': False})
            else:
                # Orden draft → liberar los que ya no están y reservar los nuevos
                to_release = previously_reserved - current_lots                 # quitaron líneas
                to_reserve = current_lots - previously_reserved                 # líneas nuevas
                if to_release:
                    to_release.write({'pos_reserved_order_id': False})
                if to_reserve:
                    to_reserve.write({'pos_reserved_order_id': order.id})

    @api.model_create_multi
    def create(self, vals_list):
        """ Al crear una orden POS, intentar reservar los lots si quedó en draft. """
        orders = super().create(vals_list)                                      # crear normalmente
        orders._idtx_sync_lot_reservations()                                    # sincronizar reservas
        return orders

    def write(self, vals):
        """
        Al modificar la orden re-sincronizar reservas.
        Sincronizamos en CUALQUIER write porque _process_order del POS hace varios writes
        (date_order, session_id, etc.) y queremos detectar cambios de estado/líneas en todos.
        La operación es idempotente (lee estado actual y solo escribe diferencias).
        """
        res = super().write(vals)                                               # escribir normalmente primero
        self._idtx_sync_lot_reservations()                                      # re-sincronizar siempre
        return res

    def unlink(self):
        """ Al eliminar la orden, ondelete='set null' libera los lots automáticamente. """
        # Liberación explícita por si el ondelete='set null' no aplicara en algún caso edge.
        self.env['stock.lot'].search([('pos_reserved_order_id', 'in', self.ids)]).write({
            'pos_reserved_order_id': False                                      # liberar antes del unlink
        })
        return super().unlink()

    @api.model
    def get_next_refund_lot_names(self, original_names):
        """
        Calcula el siguiente nombre de lote para reembolsos.
        Formato: Partida-Cnn
        """
        results = {}
        partida_counts = {} # Para manejar múltiples lotes de la misma partida en una sola llamada

        for original_name in original_names:
            if not original_name:
                continue
            
            # Extraer partida (todo lo que está antes del primer guion)
            partida = original_name.split('-')[0]
            prefix = f"{partida}-C"
            
            if partida not in partida_counts:
                # Buscar el correlativo más alto existente en la base de datos para esta partida
                existing_lots = self.env['stock.lot'].search_read(
                    [('name', '=like', f"{prefix}%")],
                    ['name']
                )
                
                max_seq = 0
                for lot in existing_lots:
                    # Buscamos el patrón -C seguido de números al final del nombre
                    match = re.search(r'-C(\d+)$', lot['name'])
                    if match:
                        try:
                            seq = int(match.group(1))
                            if seq > max_seq:
                                max_seq = seq
                        except:
                            continue
                partida_counts[partida] = max_seq
            
            # Incrementar el correlativo
            partida_counts[partida] += 1
            results[original_name] = f"{prefix}{partida_counts[partida]:02d}".upper()
            
        return results
