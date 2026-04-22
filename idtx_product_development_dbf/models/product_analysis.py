# -*- coding: utf-8 -*-

from odoo import models


class ProductAnalysis(models.Model):
    _inherit = 'product.analysis'

    def action_create_technical_sheet(self):
        existing_sheets = self.mapped('technical_sheet_ids')
        res = super().action_create_technical_sheet()
        new_sheets = self.mapped('technical_sheet_ids') - existing_sheets
        auto_export_sheets = new_sheets.filtered(lambda sheet: sheet.company_id.foxpro_auto_export_technical_sheet)
        if auto_export_sheets:
            auto_export_sheets.action_export_to_foxpro()
        return res