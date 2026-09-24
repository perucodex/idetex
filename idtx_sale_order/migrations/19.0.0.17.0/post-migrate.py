"""Fechas de precio para el widget de procesos del vendedor (JP, 23-sep-2026).

Inicializa la fecha de precio de las fases (precio por proceso), del precio de
tejido de los análisis y del recargo de las fichas de estampado con la última
modificación de cada registro: es la mejor aproximación disponible porque los
precios no llevaban seguimiento. Desde esta versión cada cambio de precio la
actualiza sola (create/write de los modelos).
"""


def migrate(cr, version):
    cr.execute("""
        UPDATE mrp_routing_workcenter_operation
           SET price_date = write_date
         WHERE price_date IS NULL
           AND unit_price > 0
    """)
    cr.execute("""
        UPDATE product_analysis
           SET weaving_price_date = write_date
         WHERE weaving_price_date IS NULL
           AND weaving_price > 0
    """)
    cr.execute("""
        UPDATE printing_design d
           SET price_date = d.write_date
         WHERE d.price_date IS NULL
           AND (d.unit_price > 0
                OR d.state = 'done'
                OR EXISTS (SELECT 1
                             FROM printing_design_price p
                            WHERE p.digital_printing_id = d.id
                              AND p.unit_price > 0))
    """)
