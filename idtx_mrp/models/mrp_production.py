# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError

class MrpProduction(models.Model):
    _inherit = 'mrp.production'

    batch_id = fields.Many2one('mrp.workorder.batch', string='Batch')

    @api.depends('bom_id', 'product_id', 'product_qty', 'product_uom_id', 'never_product_template_attribute_value_ids')
    def _compute_workorder_ids(self):
        res = super()._compute_workorder_ids()
        for rec in self:
            for wo in rec.workorder_ids:
                wo.mrwo_id = wo.operation_id.operation_id
        return res
    
    def _prepare_stock_lot_values(self):
        '''Heredamos la funcion para que el lote se cree desde la partida de rollos tejidos'''
        self.ensure_one()
        res = super()._prepare_stock_lot_values()
        if self.product_id.product_tmpl_id.is_weaving:
            if not self.batch_id:
                raise UserError(_("Please set the first Batch Number for production"))
            else:
                res['name'] = self.batch_id.name
        return res