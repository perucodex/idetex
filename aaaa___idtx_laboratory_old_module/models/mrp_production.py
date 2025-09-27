# -*- coding: utf-8 -*-

from odoo import api, models

class MrpProduction(models.Model):
    _inherit = 'mrp.production'

    @api.depends('bom_id', 'product_id', 'product_qty', 'product_uom_id', 'never_product_template_attribute_value_ids')
    def _compute_workorder_ids(self):
        res = super()._compute_workorder_ids()
        for rec in self:
            for wo in rec.workorder_ids:
                wo.mrwo_id = wo.operation_id.operation_id
        return res