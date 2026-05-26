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

    # ===== AGRUPAMIENTO DE LÍNEAS DE FACTURA POR PRODUCTO + COLOR =====
    # En el carrito y recibo, los rollos con mismo producto+color se ven agrupados.
    # Aquí hacemos lo mismo al generar la factura: N pos.order.line → 1 account.move.line.
    # Esto afecta TANTO el PDF como el XML SUNAT (ambos leen invoice_line_ids).
    # IMPORTANTE: pos.order.line se mantiene 1-por-rollo para preservar trazabilidad de stock.

    def _idtx_get_pos_line_color_key(self, pos_line):
        """ Clave para agrupar líneas: (product_id, color_name normalizado). """
        # color_name está en pos.order.line (lo guardamos al agregar el rollo al carrito)
        color = (pos_line.color_name or '').strip().upper() or 'NO_COLOR'
        return (pos_line.product_id.id, color)

    def _idtx_resolve_lots_for_pos_lines(self, pos_lines):
        """
        Resolver los lot_name de las pack_lot_ids de las líneas a stock.lot reales.
        Devuelve un recordset de stock.lot únicos (para guardar en idtx_grouped_lot_ids).
        """
        StockLot = self.env['stock.lot']
        result = StockLot.browse()
        for pos_line in pos_lines:
            for pack_lot in pos_line.pack_lot_ids:
                if not pack_lot.lot_name:
                    continue
                lot = StockLot.search([
                    ('name', '=', pack_lot.lot_name),
                    ('product_id', '=', pos_line.product_id.id),
                ], limit=1)
                if lot:
                    result |= lot
        return result

    def _prepare_invoice_lines(self, move_type):
        """
        Override: agrupar líneas de la orden POS por (producto + color) antes de crear la factura.
        Cada grupo de N rollos del mismo producto/color se convierte en 1 sola account.move.line
        con la cantidad sumada y el listado de stock.lot en idtx_grouped_lot_ids.

        Resultado: el PDF y el XML SUNAT muestran 1 línea agrupada por color en lugar de 1 por rollo.
        Por regla de negocio, todos los rollos del mismo grupo tienen el mismo price_unit.
        """
        invoice_lines = []
        for order in self:
            # line_values_list contiene un dict por cada pos.order.line con info de impuestos.
            # Lo mismo que usa el método original, pero aquí lo agrupamos antes de procesar.
            line_values_list = order.with_context(invoicing=True)._prepare_tax_base_line_values()

            # Agrupar por (producto + color). Combos van solos (no agrupan).
            groups = {}                                                         # clave → lista de line_values
            group_order = []                                                    # mantener orden de aparición
            for line_values in line_values_list:
                pos_line = line_values['record']
                if pos_line.product_id.type == 'combo':
                    key = ('combo', pos_line.id)                                # cada combo es su propia "clave"
                else:
                    key = ('group',) + order._idtx_get_pos_line_color_key(pos_line)
                if key not in groups:
                    groups[key] = []
                    group_order.append(key)
                groups[key].append(line_values)

            # Generar 1 invoice line por grupo (o 1 por combo)
            for key in group_order:
                group_line_values = groups[key]
                is_combo_or_single = key[0] == 'combo' or len(group_line_values) == 1

                if is_combo_or_single:
                    # Sin agrupar: usar la lógica original línea por línea
                    for lv in group_line_values:
                        pos_line = lv['record']
                        inv_vals = order._get_invoice_lines_values(lv, pos_line, move_type)
                        # Adjuntar el (único) lote si existe — para que el PDF lo muestre
                        if pos_line.product_id.type != 'combo':
                            lots = order._idtx_resolve_lots_for_pos_lines(pos_line)
                            if lots:
                                inv_vals['idtx_grouped_lot_ids'] = [(6, 0, lots.ids)]
                        invoice_lines.append((0, None, inv_vals))
                else:
                    # AGRUPAR: sumar quantities y usar precio/impuestos del primer rollo
                    first_lv = group_line_values[0]
                    first_pos_line = first_lv['record']

                    # Construir una copia de line_values con la cantidad agregada
                    total_qty = sum(lv['quantity'] for lv in group_line_values)
                    aggregated_lv = dict(first_lv)                              # copia superficial
                    aggregated_lv['quantity'] = total_qty                       # cantidad total del grupo

                    inv_vals = order._get_invoice_lines_values(aggregated_lv, first_pos_line, move_type)

                    # Adjuntar TODOS los lotes del grupo (para mostrar en PDF: "5 rollos" o lista)
                    pos_lines_recordset = order.env['pos.order.line'].browse(
                        [lv['record'].id for lv in group_line_values]
                    )
                    lots = order._idtx_resolve_lots_for_pos_lines(pos_lines_recordset)
                    if lots:
                        inv_vals['idtx_grouped_lot_ids'] = [(6, 0, lots.ids)]

                    invoice_lines.append((0, None, inv_vals))

                # Customer notes individuales por rollo (no se agrupan: cada rollo puede tener nota distinta)
                for lv in group_line_values:
                    pos_line = lv['record']
                    if pos_line.customer_note:
                        invoice_lines.append((0, None, {
                            'name': pos_line.customer_note,
                            'display_type': 'line_note',
                        }))

            # Nota general del cliente al final
            if order.general_customer_note:
                invoice_lines.append((0, None, {
                    'name': order.general_customer_note,
                    'display_type': 'line_note',
                }))

        return invoice_lines

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
