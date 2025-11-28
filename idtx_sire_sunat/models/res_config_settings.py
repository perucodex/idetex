# -*- coding: utf-8 -*-

from odoo import fields, models

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    client_id = fields.Char('Client ID', related='company_id.client_id', readonly=False)
    client_secret = fields.Char('Client Secret', related='company_id.client_secret', readonly=False)
    partner_annulled_id = fields.Many2one('res.partner', string='Partner Annulled', related='company_id.partner_annulled_id', readonly=False)