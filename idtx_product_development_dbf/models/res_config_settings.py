# -*- coding: utf-8 -*-

from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    foxpro_dbf_path = fields.Char(related='company_id.foxpro_dbf_path', readonly=False)
    foxpro_article_prefix = fields.Char(related='company_id.foxpro_article_prefix', readonly=False)
    foxpro_auto_export_technical_sheet = fields.Boolean(related='company_id.foxpro_auto_export_technical_sheet', readonly=False)