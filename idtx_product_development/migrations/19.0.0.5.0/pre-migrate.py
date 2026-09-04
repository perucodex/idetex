# -*- coding: utf-8 -*-
"""Retiro del catálogo de máquinas TEXPLUS (texplus.machine) y de fas_code (2026-09).

Las vistas heredadas que mostraban esos campos ya no existen en el módulo, pero
siguen en la base hasta el final de la actualización y hacen fallar la
validación de las vistas de operaciones de otros módulos. Se eliminan antes de
cargar los datos.
"""
import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)

XMLIDS = [
    'idtx_product_development.mrp_routing_workcenter_operation_form_view_texplus_machine',
    'idtx_product_development.mrp_routing_workcenter_operation_tree_view_texplus_machine',
    'idtx_product_development.texplus_machine_view_form',
    'idtx_product_development.texplus_machine_view_list',
    'idtx_product_development.texplus_machine_view_search',
    'idtx_product_development.dev_texplus_machine_menu',
    'idtx_product_development.texplus_machine_action',
]


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    for xmlid in XMLIDS:
        record = env.ref(xmlid, raise_if_not_found=False)
        if record:
            record.unlink()
            _logger.info("idtx_product_development: eliminado %s", xmlid)
