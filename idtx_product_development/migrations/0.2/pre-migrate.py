# -*- coding: utf-8 -*-
"""Migracion 0.2 (pre): limitar product_description a 26 caracteres.

Antes de que Odoo cambie la columna a varchar(26) (por el `size=26` del campo),
recortamos los pocos registros que exceden 26 caracteres; de lo contrario el
ALTER de la columna fallaria con "value too long". 26 = largo de ArtDsc en
TEXPLUS, asi que el dato ya se truncaba al exportar.
"""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    cr.execute("""
        UPDATE product_analysis
        SET product_description = left(product_description, 26)
        WHERE product_description IS NOT NULL
          AND length(product_description) > 26
    """)
    if cr.rowcount:
        _logger.info(
            "idtx_product_development 0.2: %s product_description recortados a 26 caracteres",
            cr.rowcount,
        )
