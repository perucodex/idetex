# -*- coding: utf-8 -*-
"""Migracion 0.3: el ancho de codificacion de la cuadricula de maquinas
(GRID_COLS en machine_floor.js) sube de 24 a 60 columnas, para poder mostrar
mas columnas hacia la derecha sin limite real (antes solo las filas crecian
asi, las columnas estaban fijas en 24).

slot_index se guarda como fila*GRID_COLS+columna. Con el ancho fijo, todas
las posiciones ya guardadas quedarian mal decodificadas por el frontend
(saltan de fila/columna) si no se re-codifican con el nuevo ancho.
"""
import logging

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
        "idtx_plan_general_alpha 0.3: %s filas de idtx.alpha.floor.layout "
        "re-codificadas de ancho %s a ancho %s",
        cr.rowcount, _OLD_GRID_COLS, _NEW_GRID_COLS,
    )
