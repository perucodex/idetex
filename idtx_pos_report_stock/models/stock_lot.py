# -*- coding: utf-8 -*-
# Declaración del campo pos_reserved_order_id en stock.lot.
# Vive aquí (no en idtx_pos_sale_idetex) para que la columna ya exista en stock_lot
# cuando init() crea la vista SQL idtx.pos.stock.report que lo referencia.
# La LÓGICA de reserva (hooks en pos.order) vive en idtx_pos_sale_idetex.
from odoo import models, fields


class StockLot(models.Model):
    _inherit = 'stock.lot'

    # NULL → lote disponible; con valor → lote bloqueado por un pedido POS guardado.
    # ondelete='set null' libera el lote automáticamente si la orden se elimina.
    pos_reserved_order_id = fields.Many2one(
        'pos.order',
        string='Reservado en POS',
        index=True,                                         # consulta rápida desde vista SQL
        ondelete='set null',                                # liberación automática al borrar orden
        help='Pedido POS guardado que tiene este rollo reservado. '
             'Si está vacío, el rollo está disponible para venta.'
    )
