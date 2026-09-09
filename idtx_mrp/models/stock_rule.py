# -*- coding: utf-8 -*-
from odoo import models


class StockRule(models.Model):
    _inherit = 'stock.rule'

    def _prepare_mo_vals(self, product_id, product_qty, product_uom, location_dest_id, name, origin, company_id, values, bom):
        """production_type ya no tiene default (el usuario debe elegirlo en las
        OF manuales); las OF que nacen de reglas de abastecimiento son de
        venta."""
        vals = super()._prepare_mo_vals(product_id, product_qty, product_uom, location_dest_id, name, origin, company_id, values, bom)
        vals.setdefault('production_type', 'sale')
        return vals
