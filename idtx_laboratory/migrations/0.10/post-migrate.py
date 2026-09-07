# -*- coding: utf-8 -*-
"""Nivel "Manager" de Laboratorio: es_PE "Gerente" -> "Administrador" (2026-09-07).

El .po ya dice "Administrador", pero el grupo está en un bloque noupdate y Odoo
NO sobrescribe traducciones de registros noupdate al actualizar el idioma
(TranslationImporter.save: solo con force_overwrite, que la UI no usa). Se
aplica aquí, alineado con los demás módulos (Desarrollo, Orgatex, Estampado).
"""
import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    group = env.ref('idtx_laboratory.group_module_laboratory_manager', raise_if_not_found=False)
    if not group:
        return
    es = group.with_context(lang='es_PE')
    if es.name == 'Gerente':
        es.name = 'Administrador'
        _logger.info("idtx_laboratory: nivel Manager de Laboratorio traducido a 'Administrador' (es_PE)")
