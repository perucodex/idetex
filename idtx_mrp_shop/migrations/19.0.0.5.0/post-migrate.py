# -*- coding: utf-8 -*-
"""El rollo pesado ya NO es stock hasta la recepción de almacén: la ubicación
de pesado pasa a VIRTUAL (producción) y se retira el stock que el flujo
anterior había creado ahí (rollos pesados pero aún no liberados). Los rollos
ya liberados conservan su stock en Existencias/Saldo/Mermas."""
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    # SOLO las ubicaciones de pesado de rollos configuradas en cada almacén
    # (no cualquier ubicación llamada "Pesado", que podría ser un bin real).
    weigh = env['stock.warehouse'].search(
        [('roll_weigh_location_id', '!=', False)]).roll_weigh_location_id
    if not weigh:
        return
    # retirar los quants que estaban en pesado (no debían ser stock)
    for q in env['stock.quant'].search([('location_id', 'in', weigh.ids)]).sudo():
        try:
            q.unlink()
        except Exception:
            q.inventory_quantity = 0
            q.action_apply_inventory()
    weigh.sudo().write({'usage': 'production'})
    import logging
    logging.getLogger(__name__).info(
        "idtx_mrp_shop 19.0.0.5.0: ubicaciones de pesado a producción (%s) y quants retirados",
        ', '.join(weigh.mapped('complete_name')))
