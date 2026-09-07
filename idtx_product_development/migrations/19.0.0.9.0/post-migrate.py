# -*- coding: utf-8 -*-
"""Configuración de Desarrollo solo para Administrador (2026-09-07).

El menú Configuración y sus catálogos (SVG, ligamentos, proceso base, operaciones
de centro de trabajo, Código) no tenían grupo: cualquier nivel del app los veía.
dev_menu.xml es noupdate, así que en bases ya instaladas el grupo se añade aquí.
"""
import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)

MENUS = [
    'dev_settings_menu',
    'configurate_svg_example_menu',
    'ligament_structure_menu',
    'mrp_base_operation_menu',
    'dev_mrp_routing_operation_action_menu_dev',
    'dev_product_code_menu',
]


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    mgr = env.ref('idtx_product_development.group_module_product_development_manager',
                  raise_if_not_found=False)
    if not mgr:
        return
    done = 0
    for xid in MENUS:
        menu = env.ref('idtx_product_development.%s' % xid, raise_if_not_found=False)
        if menu and mgr not in menu.group_ids:
            menu.group_ids = [(4, mgr.id)]
            done += 1
    _logger.info("idtx_product_development: Configuración restringida a Administrador (%s menús)", done)
