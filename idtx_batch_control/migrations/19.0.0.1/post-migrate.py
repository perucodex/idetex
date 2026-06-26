# -*- coding: utf-8 -*-
"""Fuerza el recálculo de las fechas de Planning por OP tras cambiar la regla
de cálculo a días hábiles (exclusión de domingos). Odoo no recalcula campos
computed almacenados ya existentes en un simple -u; aquí los marcamos como
modificados para que el flush los recompute y persista."""
import logging

from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    pedidos = env['control.pedido'].search([])
    if not pedidos:
        return
    # plan_* (fechas) dependen de feccc y plan_has_thermo; marcar feccc como
    # modificado fuerza el recompute de todas las fechas de planning.
    pedidos.modified(['feccc'])
    env.flush_all()
    _logger.info(
        "Planning por OP: fechas recalculadas (excl. domingos) en %s pedidos",
        len(pedidos),
    )
