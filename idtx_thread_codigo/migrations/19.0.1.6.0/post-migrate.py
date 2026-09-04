# -*- coding: utf-8 -*-
"""Revertir: "Gestor de Hilado" vuelve a ser nivel del selector (2026-09-04).

Se había pasado a casilla quitándole el privilege_id, pero como el grupo hereda
el Manager de Desarrollo de Producto, Odoo ocultaba los niveles Usuario/No del
selector. Se restaura el privilege_id (grupo noupdate: reponer por migración).
"""
import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    group = env.ref('idtx_thread_codigo.group_thread_manager', raise_if_not_found=False)
    priv = env.ref('idtx_product_development.module_product_development_user',
                   raise_if_not_found=False)
    if group and priv and group.privilege_id != priv:
        group.privilege_id = priv.id
        _logger.info("idtx_thread_codigo: 'Gestor de Hilado' vuelve al selector (privilege_id restaurado)")
