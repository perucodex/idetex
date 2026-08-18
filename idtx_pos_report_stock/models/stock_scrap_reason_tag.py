# -*- coding: utf-8 -*-
"""
Extensión defensiva de stock.scrap.reason.tag para garantizar que el tag
'Muestra' exista y tenga un xml_id estable del módulo (idtx_pos_report_stock.
scrap_reason_tag_muestra).

Por qué no usar <record> XML directo:
  El tag puede ya existir en la BD (creado a mano por algún usuario) sin xml_id.
  Un <record id="..." model="stock.scrap.reason.tag"> en XML chocaría con la
  constraint UNIQUE(name) y fallaría con UniqueViolation.

El patrón <function> + helper idempotente resuelve ambos casos:
  - BD nueva sin el tag → lo crea con xml_id estable.
  - BD existente con tag manual → solo asocia el xml_id sin tocar el record.
"""
from odoo import api, models


class StockScrapReasonTag(models.Model):
    _inherit = 'stock.scrap.reason.tag'

    @api.model
    def _idtx_setup_tag_muestra(self):
        """
        Idempotente: garantiza que existe un tag llamado 'Muestra' y que
        está asociado al xml_id 'idtx_pos_report_stock.scrap_reason_tag_muestra'.
        Invocado desde data/stock_scrap_reason_tag_data.xml vía <function>.
        """
        # 1. Buscar el tag existente por nombre exacto.
        tag = self.search([('name', '=', 'Muestra')], limit=1)
        # 2. Si no existe, crearlo.
        if not tag:
            tag = self.create({'name': 'Muestra'})

        # 3. Asociar el xml_id si no estuviera ya asociado.
        IMD = self.env['ir.model.data']
        existing_imd = IMD.search([
            ('module', '=', 'idtx_pos_report_stock'),
            ('name', '=', 'scrap_reason_tag_muestra'),
        ], limit=1)
        if not existing_imd:
            IMD.create({
                'module': 'idtx_pos_report_stock',
                'name': 'scrap_reason_tag_muestra',
                'model': 'stock.scrap.reason.tag',
                'res_id': tag.id,
                'noupdate': True,
            })
