# -*- coding: utf-8 -*-
"""Rollos pesados ANTES del control por rollo: ya están en stock (quant
creado al pesar), así que se dan por grado A y liberados (decisión JP,
14-sep-2026). Los lotes y quants heredan el grado (campos related stored)."""


def migrate(cr, version):
    cr.execute("""
        UPDATE mrp_production_roll r
           SET quality_grade = 'A',
               quality_state = 'released',
               quality_released = TRUE,
               quality_release_date = now(),
               quality_date = now(),
               quality_note = 'Calificación inicial automática: rollo pesado antes del control por rollo'
         WHERE r.lot_id IS NOT NULL
           AND r.quality_grade IS NULL
           AND EXISTS (SELECT 1 FROM stock_quant q WHERE q.lot_id = r.lot_id AND q.quantity > 0)
    """)
    n_rolls = cr.rowcount
    cr.execute("""
        UPDATE stock_lot l
           SET quality_grade = r.quality_grade, quality_state = r.quality_state
          FROM mrp_production_roll r
         WHERE r.id = l.roll_id AND r.quality_grade IS NOT NULL
    """)
    cr.execute("""
        UPDATE stock_quant q
           SET quality_grade = l.quality_grade
          FROM stock_lot l
         WHERE l.id = q.lot_id AND l.quality_grade IS NOT NULL
    """)
    cr.execute("""
        UPDATE mrp_workorder_batch b
           SET roll_quality_state = CASE
               WHEN NOT EXISTS (SELECT 1 FROM mrp_production_roll r WHERE r.batch_id = b.id AND r.lot_id IS NOT NULL) THEN 'none'
               WHEN NOT EXISTS (SELECT 1 FROM mrp_production_roll r WHERE r.batch_id = b.id AND r.lot_id IS NOT NULL
                                  AND r.quality_state NOT IN ('graded', 'released')) THEN 'complete'
               WHEN NOT EXISTS (SELECT 1 FROM mrp_production_roll r WHERE r.batch_id = b.id AND r.lot_id IS NOT NULL
                                  AND r.quality_state <> 'pending') THEN 'pending'
               ELSE 'partial' END
    """)
    import logging
    logging.getLogger(__name__).info("idtx_quality_control 19.0.1.1.0: %s rollos pesados marcados A/liberados", n_rolls)
