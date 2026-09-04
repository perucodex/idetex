# -*- coding: utf-8 -*-
"""Sanea menús con acción colgante (2026-09-04).

Al desinstalar los módulos SITPRO/TEXPLUS quedaron menús (algunos de Enterprise,
como el raíz de Calidad) apuntando a acciones ya borradas. Odoo intenta leer la
acción inexistente al construir el árbol de menús y devuelve un error en vez de
JSON, dejando el cliente web en blanco. Aquí se anula la acción SOLO de los menús
cuya acción referenciada ya no existe (comprobado con el ORM, que resuelve el
modelo a su tabla real; los propios se reapuntan por sus datos XML).
"""
import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    menus = env['ir.ui.menu'].with_context(active_test=False).search([('action', '!=', False)])
    cleared = 0
    for menu in menus:
        action = menu.action  # campo reference -> recordset (o False)
        try:
            missing = bool(action) and not action.exists()
        except Exception:
            missing = True
        if missing:
            menu.action = False
            cleared += 1
    if cleared:
        _logger.info("idtx_quality_control: %s menú(s) con acción colgante saneados", cleared)
