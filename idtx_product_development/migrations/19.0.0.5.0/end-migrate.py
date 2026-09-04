# -*- coding: utf-8 -*-
"""Retiro del catálogo de máquinas TEXPLUS: limpieza final.

Odoo quita los campos, permisos y restricciones del modelo desaparecido, pero
conserva la tabla y el registro ir.model ("declared but cannot be loaded").
Se eliminan aquí, al final de la carga de todos los módulos.
"""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    cr.execute("DROP TABLE IF EXISTS texplus_machine_operation_rel CASCADE")
    cr.execute("DROP TABLE IF EXISTS texplus_machine CASCADE")
    cr.execute("DELETE FROM ir_model_data WHERE model = 'ir.model' AND name = 'model_texplus_machine'")
    cr.execute("DELETE FROM ir_model WHERE model = 'texplus.machine'")
    _logger.info("idtx_product_development: tablas y registro del modelo texplus.machine eliminados")
