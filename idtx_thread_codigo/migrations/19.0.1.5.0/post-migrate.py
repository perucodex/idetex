# -*- coding: utf-8 -*-
"""El perfil "Gestor de Hilado" pasa de nivel del selector a casilla (2026-09-04).

El grupo se creó con noupdate="1", así que quitar su privilege_id del XML no lo
cambia en bases ya instaladas: se limpia aquí para que aparezca como casilla en
el formulario del usuario.
"""
import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    group = env.ref('idtx_thread_codigo.group_thread_manager', raise_if_not_found=False)
    if group and group.privilege_id:
        group.privilege_id = False
        _logger.info("idtx_thread_codigo: 'Gestor de Hilado' pasa a casilla (privilege_id vaciado)")
