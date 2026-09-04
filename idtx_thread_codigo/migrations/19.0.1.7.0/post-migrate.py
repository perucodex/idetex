# -*- coding: utf-8 -*-
"""'Gestor de Hilado' pasa a casilla-complemento (2026-09-04).

Deja de heredar el Manager de Desarrollo de Producto y de tener privilege_id, así
que ya no es un nivel del selector sino una casilla independiente. Sus permisos
sobre los catálogos de hilado ahora son propios (ir.model.access). Como el grupo
es noupdate, se hace por migración. A los usuarios que ya lo tenían (era un nivel
> Manager) se les concede el Administrador explícito para no perder acceso.
"""
import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    group = env.ref('idtx_thread_codigo.group_thread_manager', raise_if_not_found=False)
    mgr = env.ref('idtx_product_development.group_module_product_development_manager',
                  raise_if_not_found=False)
    if not group:
        return
    if mgr:
        holders = env['res.users'].search([('group_ids', 'in', group.id)])
        if holders:
            holders.write({'group_ids': [(4, mgr.id)]})
            _logger.info("idtx_thread_codigo: Administrador preservado para %s usuario(s) con 'Gestor de Hilado'", len(holders))
        if mgr in group.implied_ids:
            group.implied_ids = [(3, mgr.id)]
    if group.privilege_id:
        group.privilege_id = False
    _logger.info("idtx_thread_codigo: 'Gestor de Hilado' es ahora casilla-complemento")
