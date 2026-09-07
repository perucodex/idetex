# -*- coding: utf-8 -*-
"""Migracion 0.5: las maquinas (maintenance.equipment) creadas por este
modulo pasan a pertenecer a FULL PIMA S.A.C. (compania real de planta) en
vez de a la compania idetex bajo la que se instalo el modulo, y se les
asigna su categoria de equipo (JERSERA, GAMUZA, RIPERA... segun la primera
palabra del nombre de la maquina).

No corre solo al hacer -u (post_init_hook no se dispara en una
actualizacion, solo en la instalacion) — mismo patron que la migracion 0.4.
"""
import logging

from odoo import SUPERUSER_ID
from odoo.api import Environment

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = Environment(cr, SUPERUSER_ID, {})

    from odoo.addons.idtx_plan_general_alpha.hooks import _create_initial_equipment

    _create_initial_equipment(env)
    _logger.info('idtx_plan_general_alpha 0.5: equipos migrados a FULL PIMA S.A.C. y categorizados.')
