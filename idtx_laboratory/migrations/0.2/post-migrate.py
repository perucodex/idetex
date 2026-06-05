# -*- coding: utf-8 -*-
# Una vez creada la tabla relación m2m (lab_dev_line_product_template_rel),
# volcamos los pares (línea, producto) guardados en pre-migración y limpiamos.


def migrate(cr, version):
    if not version:
        return
    cr.execute("""
        SELECT 1 FROM information_schema.tables
        WHERE table_name = '_tmp_lab_dev_line_product'
    """)
    if not cr.fetchone():
        return
    cr.execute("""
        INSERT INTO lab_dev_line_product_template_rel (lab_dev_line_id, product_template_id)
        SELECT line_id, product_id FROM _tmp_lab_dev_line_product
        ON CONFLICT DO NOTHING
    """)
    cr.execute("DROP TABLE _tmp_lab_dev_line_product")
