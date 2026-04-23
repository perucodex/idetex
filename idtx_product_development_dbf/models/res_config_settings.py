# -*- coding: utf-8 -*-

from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    foxpro_dbf_path = fields.Char(related='company_id.foxpro_dbf_path', readonly=False)