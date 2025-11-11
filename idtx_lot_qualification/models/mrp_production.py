# -*- coding: utf-8 -*-

from odoo import fields, models, api, _

class MrpProduction(models.Model):
    _inherit = 'mrp.production'

    lot_warning = fields.Text('lot_warning', compute='_compute_lot_warning')
    is_company_produce = fields.Boolean(related='company_id.is_company_produce')

    def action_assign(self):
        for production in self:
            # Pasamos el contexto completo de producción
            production.move_raw_ids.with_context(
                mrp_production_id=production.id,
                allowed_color_intensity_ids=production.color_recipe_id.lab_dev_line_id.color_intensity_id.ids,
                allowed_product_family_ids=production.bom_id.technical_sheet_id.analysis_id.product_family_id.ids,
                is_company_produce=production.company_id.is_company_produce,
            )._action_assign()
        return super().action_assign()
    
    @api.depends('move_raw_ids')
    def _compute_lot_warning(self):
        warning = ''
        if self.is_company_produce:
            for lot in self.move_raw_ids.move_line_ids.mapped('lot_id'):
                if lot.state == 'dir':
                    if self.color_recipe_id.lab_dev_line_id.color_intensity_id in lot.color_intensity_ids:
                        warning += _('Color intensity %s is restricted in lot %s\n') % (self.color_recipe_id.lab_dev_line_id.color_intensity_id.name, lot.name)
                    if self.bom_id.technical_sheet_id.analysis_id.product_family_id in lot.product_family_ids:
                        warning += _('Product family %s is restricted in lot %s\n') % (self.bom_id.technical_sheet_id.analysis_id.product_family_id.name, lot.name)
        self.lot_warning = warning
