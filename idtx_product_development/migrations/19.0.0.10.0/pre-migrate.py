# -*- coding: utf-8 -*-
"""Catálogos con código único sembrados por CSV: adoptar registros existentes (2026-09-07).

Los CSV de data/ (product.gauge, product.title, product.fiber, product.family,
product.appearance, ligament.type) se recargan en cada upgrade. En bases donde
los usuarios ya crearon a mano un registro con el MISMO código pero sin el
xmlid del CSV (caso BD prueba = copia de prod), la carga intenta crear otro y
salta "Code must be unique!", abortando el upgrade del módulo.

Antes de cargar los datos:
- Si el xmlid del CSV no existe y hay un registro con ese código, se crea el
  xmlid apuntando a ese registro con noupdate=True: se conserva el dato de la
  BD (nombre, agujas, etc.) y el CSV deja de intentar crearlo.
- Si el xmlid existe pero su registro tiene otro código y el código del CSV lo
  usa un tercer registro, no se toca: se deja WARNING para resolverlo a mano.
"""
import csv
import logging
import os

from odoo.modules.module import get_module_path

_logger = logging.getLogger(__name__)

MODULE = 'idtx_product_development'
CSV_MODELS = [
    ('product.gauge', 'product_gauge'),
    ('product.title', 'product_title'),
    ('product.fiber', 'product_fiber'),
    ('product.family', 'product_family'),
    ('product.appearance', 'product_appearance'),
    ('ligament.type', 'ligament_type'),
]


def migrate(cr, version):
    path = get_module_path(MODULE)
    adopted = 0
    for model, table in CSV_MODELS:
        csv_path = os.path.join(path, 'data', '%s.csv' % model)
        if not os.path.exists(csv_path):
            continue
        cr.execute("SELECT to_regclass(%s)", (table,))
        if not cr.fetchone()[0]:
            continue
        with open(csv_path, newline='', encoding='utf-8') as fp:
            rows = list(csv.DictReader(fp))
        for row in rows:
            xmlid, code = (row.get('id') or '').strip(), (row.get('code') or '').strip()
            if not xmlid or not code:
                continue
            xmlid = xmlid.split('.')[-1]
            cr.execute("""SELECT res_id FROM ir_model_data
                          WHERE module = %s AND name = %s AND model = %s""", (MODULE, xmlid, model))
            data = cr.fetchone()
            cr.execute('SELECT id FROM "%s" WHERE code = %%s ORDER BY id' % table, (code,))
            same_code = [r[0] for r in cr.fetchall()]
            if data:
                if same_code and data[0] not in same_code:
                    _logger.warning(
                        "%s: %s.%s apunta al id %s pero el código %r ya lo usan los ids %s; "
                        "resolver a mano antes del upgrade", MODULE, MODULE, xmlid, data[0], code, same_code)
                continue
            if not same_code:
                continue  # el CSV lo creará normalmente
            cr.execute("""INSERT INTO ir_model_data (module, name, model, res_id, noupdate, create_date, write_date)
                          VALUES (%s, %s, %s, %s, true, now() at time zone 'UTC', now() at time zone 'UTC')""",
                       (MODULE, xmlid, model, same_code[0]))
            adopted += 1
            _logger.info("%s: %s.%s adopta el %s id %s existente con código %r (noupdate)",
                         MODULE, MODULE, xmlid, model, same_code[0], code)
            if len(same_code) > 1:
                _logger.warning("%s: código %r duplicado en %s (ids %s); se adoptó el primero",
                                MODULE, code, model, same_code)
    _logger.info("%s: pre-migrate catálogos CSV: %s registro(s) adoptado(s)", MODULE, adopted)
