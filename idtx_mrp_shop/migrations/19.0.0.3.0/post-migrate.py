# -*- coding: utf-8 -*-
"""Rollos pesados con el flujo anterior: su stock ya está en Existencias (el
quant nacía al pesar directamente ahí), así que se dan por LIBERADOS a almacén.
Los rollos nuevos entran a la ubicación de pesado y se liberan con la recepción."""


def migrate(cr, version):
    cr.execute("""
        UPDATE mrp_production_roll r
           SET quality_released = TRUE,
               quality_release_date = COALESCE(r.quality_release_date, now()),
               quality_state = 'released'
         WHERE r.lot_id IS NOT NULL
           AND r.quality_grade IS NOT NULL
           AND NOT r.quality_released
           AND EXISTS (SELECT 1 FROM stock_quant q
                         JOIN stock_location l ON l.id = q.location_id
                        WHERE q.lot_id = r.lot_id AND q.quantity > 0 AND l.usage = 'internal')
    """)
    cr.execute("""
        UPDATE stock_lot l SET quality_state = r.quality_state
          FROM mrp_production_roll r WHERE r.id = l.roll_id
    """)
