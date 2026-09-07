# -*- coding: utf-8 -*-
"""Migracion 0.4: restaura el layout canonico de maquinas (definido a mano
en hooks.py, por serial_no) sobre idtx.alpha.floor.layout.

Por que hace falta: la migracion 0.3 (24->60 columnas de codificacion) solo
re-codifico las filas YA GUARDADAS en la base, preservando su posicion
visual exacta. Pero mientras se probaba el arrastre/redimensionado en el
dashboard (con versiones del JS que todavia tenian bugs de esa misma
migracion), se guardaron varias posiciones incorrectas encima de las
correctas. hooks.py._create_floor_layouts ya sabe "crear o corregir" de
forma idempotente comparando contra el layout de disenio original — esta
migracion simplemente la vuelve a invocar (ya con hooks.py corregido para
convertir esos datos, disenados en base 24, a la codificacion actual de 60)
para devolver cada maquina a su posicion/tamanio de disenio.

Nota: esto NO corre solo al reinstalar (post_init_hook no se dispara en un
simple -u), por eso hace falta como migracion explicita.
"""
import logging

from odoo import SUPERUSER_ID
from odoo.api import Environment

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = Environment(cr, SUPERUSER_ID, {})

    from odoo.addons.idtx_plan_general_alpha.hooks import (
        _create_floor_layouts,
        _TEJEDURIA_FLOOR_LAYOUT,
        _TINTORERIA_FLOOR_LAYOUT,
    )

    _create_floor_layouts(env, 'TEJEDURIA', _TEJEDURIA_FLOOR_LAYOUT)
    _create_floor_layouts(env, 'TINTORERIA', _TINTORERIA_FLOOR_LAYOUT)
    _logger.info('idtx_plan_general_alpha 0.4: layout canonico de piso restaurado.')
