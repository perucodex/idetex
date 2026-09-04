# -*- coding: utf-8 -*-
"""Retiro de la integración TEXPLUS (2026-09).

El cron "Sincronizar procesos base TEXPLUS" se cargó con noupdate="1", así que
quitarlo del XML del módulo no lo elimina de la base: se borra aquí. Se usa el
ORM porque ir.cron hereda (_inherits) de ir.actions.server y un DELETE directo
dejaría huérfana la acción de servidor.
"""
import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    cron = env.ref('idtx_product_development.ir_cron_sync_texplus_base_process', raise_if_not_found=False)
    if cron:
        cron.unlink()
        _logger.info("idtx_product_development: cron de sincronización TEXPLUS eliminado")
    # Residuos de otros módulos legacy ya desinstalados (por si quedó alguno).
    leftovers = env['ir.cron'].sudo().with_context(active_test=False).search([
        '|', ('cron_name', 'ilike', 'TEXPLUS'), ('cron_name', 'ilike', 'SITPRO'),
    ])
    if leftovers:
        _logger.info("idtx_product_development: crons legacy eliminados: %s", leftovers.mapped('cron_name'))
        leftovers.unlink()
