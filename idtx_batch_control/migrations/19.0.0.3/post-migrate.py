# -*- coding: utf-8 -*-
"""Recalcula los kilos teñidos / % avance tras afinar el match de la fase de
teñido (ahora excluye RETEÑIDO y SUAVIZADO EN MAQ TEÑIDO). Los campos computed
almacenados no se recalculan solos en un -u cuando solo cambia la lógica."""
import logging

from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    pedidos = env['control.pedido'].search([])
    if not pedidos:
        return
    pedidos._compute_plan_kilos_dyed()
    pedidos._compute_plan_dye_progress()
    pedidos.flush_recordset(['plan_kilos_dyed', 'plan_dye_progress'])
    _logger.info(
        "Planning por OP: kilos teñidos / %% avance recalculados (excl. "
        "RETEÑIDO y SUAVIZADO) en %s pedidos", len(pedidos))
