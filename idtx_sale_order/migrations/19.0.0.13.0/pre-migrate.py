# -*- coding: utf-8 -*-
"""sitpro.sale.type: order_kind pasa de las letras SITPRO (S/V/F) a claves
legibles (service/sale/sale_stock) y desaparece el campo code (2026-09-10).

Se corre ANTES de actualizar el módulo porque, al retirar los valores viejos de
la selección, Odoo pondría order_kind en NULL en todos los registros (ondelete
'set null' de ir.model.fields.selection). La columna code queda huérfana
(Odoo no borra columnas) pero era NOT NULL: sin quitar la restricción no se
podría crear ningún tipo de proceso nuevo.

En bases donde el legacy idtx_sale_sitpro se DESINSTALÓ antes de esta versión
(BD prueba del servidor .18, 04-sep-2026) la desinstalación ya borró la tabla:
no hay nada que migrar y el upgrade crea sitpro_sale_type de cero con la data
semilla del módulo (data/sitpro_sale_type_data.xml).
"""


def migrate(cr, version):
    cr.execute("SELECT to_regclass('sitpro_sale_type')")
    if not cr.fetchone()[0]:
        return
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
