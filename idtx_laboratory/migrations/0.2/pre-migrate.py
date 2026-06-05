# -*- coding: utf-8 -*-
# Antes de cargar el modelo (que reemplaza product_id m2o por product_ids m2m),
# guardamos en una tabla temporal el producto actual de cada lab.dev.line para
# no perderlo. La tabla relación m2m todavía no existe en pre-migración.


def migrate(cr, version):
    if not version:
        return
    cr.execute("""
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'lab_dev_line' AND column_name = 'product_id'
    """)
    if not cr.fetchone():
        return
    cr.execute("""
        CREATE TABLE IF NOT EXISTS _tmp_lab_dev_line_product AS
        SELECT id AS line_id, product_id
        FROM lab_dev_line
        WHERE product_id IS NOT NULL
    """)
