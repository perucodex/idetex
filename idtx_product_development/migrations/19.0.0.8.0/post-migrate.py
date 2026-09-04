# -*- coding: utf-8 -*-
"""'Editor de Precio' pasa a casilla-complemento (2026-09-04).

Deja de heredar el Manager de Desarrollo de Producto y de tener privilege_id, así
que ya no es un nivel del selector sino una casilla independiente (solo desbloquea
los campos de precio, gateados también con este grupo). Como el grupo es noupdate,
se hace por migración. A los usuarios que ya lo tenían (era un nivel > Manager) se
les concede el Administrador explícito para no perder acceso.
"""
import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    group = env.ref('idtx_product_development.group_module_product_development_price_editor',
                    raise_if_not_found=False)
    mgr = env.ref('idtx_product_development.group_module_product_development_manager',
                  raise_if_not_found=False)
    if not group:
        return
    if mgr:
        holders = env['res.users'].search([('group_ids', 'in', group.id)])
        if holders:
            holders.write({'group_ids': [(4, mgr.id)]})
            _logger.info("idtx_product_development: Administrador preservado para %s usuario(s) con 'Editor de Precio'", len(holders))
        if mgr in group.implied_ids:
            group.implied_ids = [(3, mgr.id)]
    if group.privilege_id:
        group.privilege_id = False
    _logger.info("idtx_product_development: 'Editor de Precio' es ahora casilla-complemento")
