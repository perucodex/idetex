# -*- coding: utf-8 -*-
"""Recalcula Kilos x Teñir (ahora = total_weight/TOTKIL, el total pedido, en
vez de la suma de partidas) y el % avance (topado a 100%). Los campos computed
almacenados no se recalculan solos en un -u cuando solo cambia la lógica."""
import logging

from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    pedidos = env['control.pedido'].search([])
    if not pedidos:
        return
    pedidos._compute_plan_kilos_to_dye()
    pedidos._compute_plan_dye_progress()
    pedidos.flush_recordset(['plan_kilos_to_dye', 'plan_dye_progress'])
    _logger.info(
        "Planning por OP: Kilos x Teñir (= total pedido) y %% avance "
        "recalculados en %s pedidos", len(pedidos))
