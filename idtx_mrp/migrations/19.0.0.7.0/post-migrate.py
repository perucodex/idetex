# -*- coding: utf-8 -*-
"""N° de rollo (Acabado) para los rollos ya pesados: hasta ahora el sufijo del
lote era el orden de pesado; se toma ese sufijo como N° rollo para no romper
la identidad de los lotes existentes."""


def migrate(cr, version):
    cr.execute("""
        UPDATE mrp_production_roll r
           SET roll_num = split_part(l.name, '-', 2)::integer
          FROM stock_lot l
         WHERE l.id = r.lot_id AND r.roll_num IS NULL
           AND l.name ~ '-[0-9]+$'
    """)
