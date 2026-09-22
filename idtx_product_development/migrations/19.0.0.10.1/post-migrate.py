# -*- coding: utf-8 -*-
"""Estado de producción a nivel de ANÁLISIS (JP, 21-sep-2026).

technical.sheet.production_state (texto Sample/Pilot/Production, escrito al
terminar una OF) pasa a product.analysis.production_state (selección
product/sample/pilot/production, nunca retrocede). Se puebla con el MÁXIMO de:

1. el estado de las fichas técnicas de cada análisis (columna antigua, que
   Odoo deja huérfana en BD), y
2. las OF terminadas de los productos del análisis (venta/servicio/reposición
   → production, piloto → pilot, muestra → sample).

Corre DESPUÉS de crear la columna nueva (todas las filas nacen en 'product').
"""
import logging

_logger = logging.getLogger(__name__)

RANK_SQL = "CASE %s WHEN 'production' THEN 3 WHEN 'pilot' THEN 2 WHEN 'sample' THEN 1 ELSE 0 END"


def migrate(cr, version):
    cr.execute("""
        SELECT 1 FROM information_schema.columns
         WHERE table_name = 'technical_sheet' AND column_name = 'production_state'
    """)
    if cr.fetchone():
        cr.execute("""
            UPDATE product_analysis a
               SET production_state = s.st
              FROM (
                SELECT analysis_id,
                       CASE MAX(CASE production_state
                                    WHEN 'Production' THEN 3 WHEN 'Pilot' THEN 2
                                    WHEN 'Sample' THEN 1 ELSE 0 END)
                            WHEN 3 THEN 'production' WHEN 2 THEN 'pilot' WHEN 1 THEN 'sample'
                       END AS st
                  FROM technical_sheet
                 WHERE analysis_id IS NOT NULL AND production_state IS NOT NULL
                 GROUP BY analysis_id
              ) s
             WHERE s.analysis_id = a.id AND s.st IS NOT NULL
        """)
        _logger.info('idtx_product_development: estado de producción copiado desde fichas en %s análisis', cr.rowcount)

    cr.execute("""
        UPDATE product_analysis a
           SET production_state = m.st
          FROM (
            SELECT pt.analysis_id,
                   CASE MAX(CASE mp.production_type
                                WHEN 'sale' THEN 3 WHEN 'service' THEN 3 WHEN 'reposicion' THEN 3
                                WHEN 'pilot' THEN 2 WHEN 'sample' THEN 1 ELSE 0 END)
                        WHEN 3 THEN 'production' WHEN 2 THEN 'pilot' WHEN 1 THEN 'sample'
                   END AS st
              FROM mrp_production mp
              JOIN product_product pp ON pp.id = mp.product_id
              JOIN product_template pt ON pt.id = pp.product_tmpl_id
             WHERE mp.state = 'done' AND pt.analysis_id IS NOT NULL
             GROUP BY pt.analysis_id
          ) m
         WHERE m.analysis_id = a.id AND m.st IS NOT NULL
           AND (%s) > (%s)
    """ % (RANK_SQL % 'm.st', RANK_SQL % 'a.production_state'))
    _logger.info('idtx_product_development: estado de producción subido desde OF terminadas en %s análisis', cr.rowcount)
