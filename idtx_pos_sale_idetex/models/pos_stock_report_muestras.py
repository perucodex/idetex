# -*- coding: utf-8 -*-
"""
Extensión de idtx.pos.stock.report para agregar un label legible del pedido
que bloquea cada rollo.

Nota histórica: este archivo se llamó originalmente pos_stock_report_muestras.py
porque también contenía la lógica de "muestras" (sample_qty, idtx_is_sample,
override de init() para separar quantity vs sample_qty). Esa funcionalidad fue
removida el 2026-06-25 en favor de las herramientas nativas de Odoo
(stock.scrap con tag "Muestra" + Ajuste de inventario para devoluciones).

Lo único que sobrevive aquí es `reserved_by_order_label`, que no tiene
relación con muestras y sigue siendo útil.
"""
from odoo import models, fields, api


class IdtxPosStockReportMuestras(models.Model):
    _inherit = 'idtx.pos.stock.report'

    # Label legible del pedido que bloquea el rollo.
    # La columna nativa `reserved_by_order_id` (Many2one) muestra el `name` de
    # la pos.order, que para pedidos en estado 'draft' es literalmente '/' (placeholder
    # de Odoo hasta que se valide). Este campo arma un texto descriptivo usando
    # tracking_number + pos_reference que SÍ están disponibles en draft.
    reserved_by_order_label = fields.Char(
        string='Pedido que bloquea',
        compute='_compute_reserved_by_order_label',
        help='Identificador legible del pedido POS que tiene reservado este rollo. '
             'Combina el número de ticket (visible al cliente) y la referencia POS interna.',
    )

    @api.depends('reserved_by_order_id')
    def _compute_reserved_by_order_label(self):
        """
        Arma un label descriptivo del pedido que bloquea el rollo, p.ej:
          "Ticket #64006 — (2664-1-000006)"
        Si el pedido ya fue validado (tiene name distinto de '/'), usa el name
        oficial como primer dato.

        Razón: para pedidos en estado 'draft' (POS save guardado pero no cobrado),
        el campo `name` es '/' y la columna Many2one muestra eso. Aquí construimos
        un texto útil aunque el pedido aún no tenga nombre asignado.
        """
        for rec in self:
            order = rec.reserved_by_order_id
            if not order:
                rec.reserved_by_order_label = ''
                continue

            partes = []
            # 1) Si el pedido ya tiene name "real" (no es el placeholder '/'), úsalo
            if order.name and order.name != '/':
                partes.append(order.name)
            # 2) Tracking number = ticket que ve el cliente en el recibo
            if order.tracking_number:
                partes.append(f"Ticket #{order.tracking_number}")
            # 3) pos_reference = referencia POS interna (config-sesion-correlativo)
            if order.pos_reference:
                partes.append(f"({order.pos_reference})")

            rec.reserved_by_order_label = ' — '.join(partes) if partes else order.display_name
