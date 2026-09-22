# -*- coding: utf-8 -*-
"""is_printing de la línea pasa a reconocer el estampado por el toggle
"¿Estampa el producto?" de la fase (prints_product, idtx_printing) en vez del
tipo 'printing' del centro de trabajo (JP, 22-sep-2026). Odoo no recalcula un
campo almacenado al cambiar sus depends: se recalcula aquí (sin tocar
printing_design_id) y se registra qué líneas cambian.

Reparación previa: las fases que estampan solían no tener precio por proceso y
por eso NO quedaban entre las operaciones elegidas de las líneas antiguas
(antes no eran seleccionables). Donde la ruta del análisis tiene una fase que
estampa y la línea tiene diseño (o es venta, donde se eligen todas las fases
cotizables) se agrega a operation_ids para que is_printing no caiga a falso
con diseño puesto. Un servicio sin diseño se respeta (el vendedor pudo quitar
el estampado a propósito).
"""
import logging

from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    lines = env['sale.order.line'].search([('is_weaving', '=', True)])
    before = {l.id: l.is_printing for l in lines}
    # La relación se completa por SQL, no por write(): escribir operation_ids
    # recalcula price_unit (en pedidos vuelve a buscar la cotización y puede
    # fallar o mover precios confirmados) y rehace las OT de las OF en borrador.
    to_insert, repaired = [], env['sale.order.line']
    for line in lines:
        if not line.operation_ids:
            continue
        missing = line._get_analysis_route_operations().filtered('prints_product') - line.operation_ids
        if missing and (line.printing_design_id or line.order_id.sale_type == 'sale'):
            to_insert.extend((line.id, op.id) for op in missing)
            repaired |= line
    if to_insert:
        cr.executemany(
            "INSERT INTO sale_order_line_mrwo_rel (line_id, operation_id) VALUES (%s, %s) "
            "ON CONFLICT DO NOTHING", to_insert)
        env.invalidate_all()
    _logger.info(
        'idtx_sale_order: fase de estampado agregada a las operaciones de %s líneas: %s',
        len(repaired), ', '.join(sorted(set(repaired.mapped('order_id.name')))) or '-')
    lines._compute_is_printing()
    env.flush_all()
    changed = lines.filtered(lambda l: before[l.id] != l.is_printing)
    _logger.info(
        'idtx_sale_order: is_printing recalculado por toggle "Estampa el producto" en %s líneas; '
        'cambiaron %s: %s', len(lines), len(changed),
        ', '.join(sorted(set(changed.mapped('order_id.name')))) or '-')
