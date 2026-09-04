# -*- coding: utf-8 -*-
"""El perfil "Editor de Precio" pasa de nivel del selector a casilla (2026-09-04).

El grupo se creó con noupdate="1", así que quitar su privilege_id del XML no lo
cambia en bases ya instaladas: se limpia aquí para que aparezca como casilla en
el formulario del usuario.
"""
import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    group = env.ref('idtx_product_development.group_module_product_development_price_editor',
                    raise_if_not_found=False)
    if group and group.privilege_id:
        group.privilege_id = False
        _logger.info("idtx_product_development: 'Editor de Precio' pasa a casilla (privilege_id vaciado)")
