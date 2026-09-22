# -*- coding: utf-8 -*-
"""Portado de la rama 19.0 (migraciones 0.3, 0.4 y 0.5 del módulo allí) a la
numeración de `prueba` (19.0.1.0.0 → 19.0.1.1.0), 22-sep-2026. Las tres
corren en este orden:

1. (0.3) La codificación de la cuadrícula del piso de máquinas sube de 24 a
   60 columnas (GRID_COLS en models/floor_layout.py): slot_index se guarda
   como fila*GRID_COLS+columna, así que las posiciones ya guardadas se
   re-codifican para no saltar de fila/columna en el frontend.
2. (0.4) Se restaura el layout canónico de máquinas definido en hooks.py
   (por serial_no), ya convertido a la codificación de 60 columnas.
3. (0.5) Los equipos creados por el módulo pasan a FULL PIMA S.A.C.
   (compañía real de planta) y reciben su categoría (JERSERA, GAMUZA…,
   primera palabra del nombre). Va acompañado de sudo() en las lecturas de
   equipos de idtx_mrp/models/mrp_workorder.py.

post_init_hook no corre en un -u: por eso hace falta la migración explícita.
"""
import logging

from odoo import SUPERUSER_ID
from odoo.api import Environment

_logger = logging.getLogger(__name__)

_OLD_GRID_COLS = 24
_NEW_GRID_COLS = 60


def migrate(cr, version):
    cr.execute(
        """
        UPDATE idtx_alpha_floor_layout
           SET slot_index = (slot_index / %(old)s) * %(new)s + (slot_index %% %(old)s)
        """,
        {"old": _OLD_GRID_COLS, "new": _NEW_GRID_COLS},
    )
    _logger.info(
        "idtx_plan_general_alpha 19.0.1.1.0: %s posiciones de piso re-codificadas de %s a %s columnas",
        cr.rowcount, _OLD_GRID_COLS, _NEW_GRID_COLS,
    )

    env = Environment(cr, SUPERUSER_ID, {})
    from odoo.addons.idtx_plan_general_alpha.hooks import (
        _create_floor_layouts,
        _create_initial_equipment,
        _TEJEDURIA_FLOOR_LAYOUT,
        _TINTORERIA_FLOOR_LAYOUT,
    )

    _create_floor_layouts(env, 'TEJEDURIA', _TEJEDURIA_FLOOR_LAYOUT)
    _create_floor_layouts(env, 'TINTORERIA', _TINTORERIA_FLOOR_LAYOUT)
    _logger.info('idtx_plan_general_alpha 19.0.1.1.0: layout canónico de piso restaurado.')

    _create_initial_equipment(env)
    _logger.info('idtx_plan_general_alpha 19.0.1.1.0: equipos migrados a FULL PIMA S.A.C. y categorizados.')
