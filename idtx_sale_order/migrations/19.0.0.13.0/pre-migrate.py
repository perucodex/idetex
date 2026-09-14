# -*- coding: utf-8 -*-
"""sitpro.sale.type: order_kind pasa de las letras SITPRO (S/V/F) a claves
legibles (service/sale/sale_stock) y desaparece el campo code (2026-09-10).

Se corre ANTES de actualizar el módulo porque, al retirar los valores viejos de
la selección, Odoo pondría order_kind en NULL en todos los registros (ondelete
'set null' de ir.model.fields.selection). La columna code queda huérfana
(Odoo no borra columnas) pero era NOT NULL: sin quitar la restricción no se
podría crear ningún tipo de proceso nuevo.
"""


def migrate(cr, version):
    cr.execute("""
        UPDATE sitpro_sale_type
           SET order_kind = CASE order_kind
                                WHEN 'S' THEN 'service'
                                WHEN 'V' THEN 'sale'
                                WHEN 'F' THEN 'sale_stock'
                            END
         WHERE order_kind IN ('S', 'V', 'F')
    """)
    cr.execute("""
        SELECT 1 FROM information_schema.columns
         WHERE table_name = 'sitpro_sale_type' AND column_name = 'code' AND is_nullable = 'NO'
    """)
    if cr.fetchone():
        cr.execute("ALTER TABLE sitpro_sale_type ALTER COLUMN code DROP NOT NULL")
