# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError

class MrpProduction(models.Model):
    _inherit = 'mrp.production'

    @api.onchange('production_type')
    def _onchange_production_type(self):
        for rec in self:
            if rec.product_id.product_tmpl_id.analysis_id.production_state == 'Production' and rec.production_type == 'pilot':
                raise UserError(_('Product is in Production state!'))
            elif rec.product_id.product_tmpl_id.analysis_id.production_state == 'Pilot' and rec.production_type == 'sample':
                raise UserError(_('Product is in Pilot state'))

    def button_mark_done(self):
        res = super().button_mark_done()
        for rec in self:
            if not rec.production_type:
                raise UserError(_('Please select a production type before marking as done.'))
            if rec.production_type == 'sale' or rec.production_type == 'service':
                prod_state = 'Production'
            elif rec.production_type == 'pilot':
                prod_state = 'Pilot'
            elif rec.production_type == 'sample':
                prod_state = 'Sample'
            rec.product_id.product_tmpl_id.analysis_id.production_state = prod_state
        return res