# -*- coding: utf-8 -*-
"""Cotización con la ruta del análisis del producto (21-sep-2026).

sale.order.line.operation_ids pasa de operaciones de la LdM
(mrp.routing.workcenter, tabla mrp_routing_workcenter_sale_order_line_rel) a
fases del maestro (mrp.routing.workcenter.operation, tabla nueva
sale_order_line_mrwo_rel). Se traducen las selecciones existentes por la fase
maestra de cada operación de LdM (mrp_routing_workcenter.operation_id) para
que las cotizaciones/pedidos conserven sus procesos cotizados.

Corre DESPUÉS de actualizar el módulo (la tabla nueva ya existe). La tabla
vieja se deja tal cual (Odoo no la borra); se puede eliminar a mano cuando
esté verificado el traspaso.

Además se recalculan los flags almacenados que antes salían de la LdM
(has_weaving_operation, is_lab_color, is_printing): Odoo no recalcula un
campo almacenado al cambiar sus depends, y donde la ruta de la ficha divergía
de la del análisis quedarían con el valor viejo. Se registra en el log cuántas
líneas cambian.
"""
import logging

from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    cr.execute("""
        SELECT 1 FROM information_schema.tables
         WHERE table_name = 'mrp_routing_workcenter_sale_order_line_rel'
    """)
    if cr.fetchone():
        cr.execute("""
            INSERT INTO sale_order_line_mrwo_rel (line_id, operation_id)
            SELECT DISTINCT r.sale_order_line_id, w.operation_id
              FROM mrp_routing_workcenter_sale_order_line_rel r
              JOIN mrp_routing_workcenter w ON w.id = r.mrp_routing_workcenter_id
              JOIN sale_order_line l ON l.id = r.sale_order_line_id
             WHERE w.operation_id IS NOT NULL
            ON CONFLICT DO NOTHING
        """)
        _logger.info('idtx_sale_order: %s operaciones cotizadas traspasadas a fases del maestro', cr.rowcount)

    env = api.Environment(cr, SUPERUSER_ID, {})
    lines = env['sale.order.line'].search([('is_weaving', '=', True)])
    before = {l.id: (l.has_weaving_operation, l.is_lab_color, l.is_printing) for l in lines}
    lines._compute_has_weaving_operation()
    lines._compute_is_lab_color()
    lines._compute_is_printing()
    env.flush_all()
    changed = lines.filtered(
        lambda l: before[l.id] != (l.has_weaving_operation, l.is_lab_color, l.is_printing))
    _logger.info(
        'idtx_sale_order: flags de ruta recalculados con la ruta del análisis en %s líneas de tejido; '
        'cambiaron %s: %s', len(lines), len(changed),
        ', '.join(sorted(set(changed.mapped('order_id.name')))) or '-')
