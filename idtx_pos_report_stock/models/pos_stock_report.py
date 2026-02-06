# -*- coding: utf-8 -*-
from odoo import models, fields, api, tools

class IdtxPosStockReport(models.Model):
    _name = "idtx.pos.stock.report"
    _description = "Reporte de Existencias PdV"
    _auto = False
    _table = "idtx_pos_stock_report"

    # Campos de Navegación (IDs)
    product_id = fields.Many2one('product.product', string='Producto', readonly=True)
    lot_id = fields.Many2one('stock.lot', string='Lote', readonly=True)
    roll_id = fields.Many2one('mrp.production.roll', string='Referencia', readonly=True)
    
    # Campos de Búsqueda/Texto (JSONB Logic)
    product_name = fields.Char('Descripción Producto', readonly=True)
    product_code = fields.Char('Código Producto', readonly=True)
    lot_name = fields.Char('Número de Lote', readonly=True)
    roll_name = fields.Char('Número de Referencia', readonly=True)

    # Campos de Color (Manejados vía SQL Join en init)
    color_code = fields.Char('Código Color', readonly=True)
    color_name = fields.Char('Nombre Color', readonly=True)
    
    quantity = fields.Float('Stock (Kg)', readonly=True)
    location_id = fields.Many2one('stock.location', string='Ubicación', readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW %s AS (
                SELECT
                    q.id AS id,
                    q.product_id AS product_id,
                    pt.default_code AS product_code,
                    COALESCE(pt.name->>'es_PE', pt.name->>'en_US', pt.name->>'und') AS product_name,
                    q.lot_id AS lot_id,
                    l.name AS lot_name,
                    ldl.color_code AS color_code,
                    ldl.color_name AS color_name,
                    r.id AS roll_id,
                    r.name AS roll_name,
                    q.quantity AS quantity,
                    q.location_id AS location_id
                FROM
                    stock_quant q
                JOIN
                    product_product pp ON pp.id = q.product_id
                JOIN
                    product_template pt ON pt.id = pp.product_tmpl_id
                LEFT JOIN
                    stock_lot l ON l.id = q.lot_id
                LEFT JOIN
                    color_recipe cr ON cr.id = l.color_recipe_id
                LEFT JOIN
                    lab_dev_line ldl ON ldl.id = cr.lab_dev_line_id
                LEFT JOIN
                    mrp_production_roll r ON r.lot_id = l.id
                WHERE
                    q.quantity > 0
                    AND pt.available_in_pos = True
            )
        """ % self._table)
