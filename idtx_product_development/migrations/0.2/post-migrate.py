# -*- coding: utf-8 -*-
"""Migracion 0.2: weaving_category_ids / thread_category_ids pasan de One2many
(Many2one en product.category) a Many2many.

Copia el dato de los antiguos Many2one (que quedan como columnas huerfanas tras
el cambio de campo) a las nuevas tablas relacionales M2M, para no perder la
configuracion de categorias de tejido/hilado por compania. Luego elimina las
columnas viejas.
"""
import logging

_logger = logging.getLogger(__name__)

# (columna_vieja_en_product_category, tabla_rel_m2m_nueva)
_MAPPING = [
    ('thread_company_categ_id', 'company_thread_category_rel'),
    ('weaving_company_categ_id', 'company_weaving_category_rel'),
]


def migrate(cr, version):
    for old_col, rel in _MAPPING:
        # ¿Existe aun la columna vieja? (idempotente si la migracion re-corre)
        cr.execute(
            """
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'product_category' AND column_name = %s
            """,
            (old_col,),
        )
        if not cr.fetchone():
            continue

        cr.execute(
            f"""
            INSERT INTO {rel} (company_id, category_id)
            SELECT pc.{old_col}, pc.id
            FROM product_category pc
            WHERE pc.{old_col} IS NOT NULL
              AND NOT EXISTS (
                  SELECT 1 FROM {rel} r
                  WHERE r.company_id = pc.{old_col} AND r.category_id = pc.id
              )
            """
        )
        copied = cr.rowcount
        cr.execute(f"ALTER TABLE product_category DROP COLUMN {old_col}")
        _logger.info(
            "idtx_product_development 0.2: migradas %s filas a %s (columna %s eliminada)",
            copied, rel, old_col,
        )
