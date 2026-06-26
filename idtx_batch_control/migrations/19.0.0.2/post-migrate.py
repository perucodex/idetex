# -*- coding: utf-8 -*-
"""Recalcula los campos de avance de teñido del Planning por OP.

`plan_dye_progress` ya existía y su lógica cambió (ahora el denominador es
`plan_kilos_to_dye` = suma de kilos de las partidas, en vez de `total_weight`).
Odoo no recomputa campos computed almacenados ya existentes en un simple -u, así
que aquí forzamos el recálculo de los tres campos en orden de dependencia."""
import logging

from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    pedidos = env['control.pedido'].search([])
    if not pedidos:
        return
    pedidos._compute_plan_kilos_to_dye()
    pedidos._compute_plan_kilos_dyed()
    pedidos._compute_plan_dye_progress()
    pedidos.flush_recordset(
        ['plan_kilos_to_dye', 'plan_kilos_dyed', 'plan_dye_progress'])
    _logger.info(
        "Planning por OP: kilos a teñir / teñidos / %% avance recalculados en "
        "%s pedidos", len(pedidos))
