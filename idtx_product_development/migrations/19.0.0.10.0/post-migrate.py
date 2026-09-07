# -*- coding: utf-8 -*-
"""Proceso base propio por ficha técnica (2026-09-07).

technical.sheet.mrp_base_process_id deja de ser related del análisis y pasa a
columna propia: cada ficha nace con el proceso base de su análisis y el usuario
puede cambiarlo solo en esa ficha. Se inicializa desde el análisis para que todas
las fichas existentes sigan al análisis (misma ruta base), como hasta ahora.
"""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    cr.execute("""
        UPDATE technical_sheet ts
           SET mrp_base_process_id = pa.mrp_base_process_id
          FROM product_analysis pa
         WHERE pa.id = ts.analysis_id
           AND ts.mrp_base_process_id IS NULL
           AND pa.mrp_base_process_id IS NOT NULL
    """)
    _logger.info("idtx_product_development: proceso base propio inicializado en %s fichas", cr.rowcount)
