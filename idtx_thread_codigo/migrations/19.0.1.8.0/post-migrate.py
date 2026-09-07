# -*- coding: utf-8 -*-
"""El Gestor de Hilado ve el menú Configuración de Desarrollo (2026-09-07).

Configuración pasó a exigir Administrador de Desarrollo de Producto. El Gestor de
Hilado necesita ese menú padre para llegar a sus catálogos (Título, Cabos, ...),
así que se le añade como grupo alternativo del menú (OR entre grupos). El menú es
noupdate en idtx_product_development: en bases ya instaladas se aplica aquí.
"""
import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    menu = env.ref('idtx_product_development.dev_settings_menu', raise_if_not_found=False)
    group = env.ref('idtx_thread_codigo.group_thread_manager', raise_if_not_found=False)
    if menu and group and group not in menu.group_ids:
        menu.group_ids = [(4, group.id)]
        _logger.info("idtx_thread_codigo: 'Gestor de Hilado' añadido al menú Configuración de Desarrollo")
