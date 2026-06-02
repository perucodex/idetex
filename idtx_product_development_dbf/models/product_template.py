# -*- coding: utf-8 -*-
import logging

from odoo import api, models

_logger = logging.getLogger(__name__)


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    def _sync_spinning_from_sitpro(self):
        """Actualiza Cod. Proceso / Proceso / Linea de hilado desde SITPRO para
        los productos en `self` que tengan default_code.

        Consulta en lote `codigohilocrud -> hil_proceso / hil_linea`. Solo
        escribe los productos cuyo codigo exista en SITPRO; los que no aparecen
        se dejan sin tocar (no se borran datos previos)."""
        products = self.filtered(lambda p: p.default_code)
        if not products:
            return
        codes = list({(p.default_code or '').strip() for p in products})
        data_by_code = self.env['technical.sheet']._get_yarn_process_data_bulk(codes)
        if not data_by_code:
            return
        updated = 0
        for product in products:
            data = data_by_code.get((product.default_code or '').strip())
            if not data:
                continue
            vals = {
                'spinning_process_code': data.get('codpro') or False,
                'spinning_process': data.get('proceso') or False,
                'spinning_line': data.get('linea') or False,
            }
            # Evita writes innecesarios (y churn en el log de auditoria).
            if any(product[f] != v for f, v in vals.items()):
                product.write(vals)
                updated += 1
        _logger.info(
            "product.template: hilado SITPRO sincronizado (%s de %s productos)",
            updated, len(products),
        )

    @api.model
    def _cron_sync_spinning_from_sitpro(self):
        """Cron: sincroniza los datos de hilado de todos los productos con
        codigo desde SITPRO."""
        products = self.search([('default_code', '!=', False)])
        products._sync_spinning_from_sitpro()
