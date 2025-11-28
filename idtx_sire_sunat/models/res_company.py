# -*- coding: utf-8 -*-

from odoo import fields, models

class ResCompany(models.Model):
    _inherit = 'res.company'

    client_id = fields.Char('Client ID')
    client_secret = fields.Char('Client Secret')
    partner_annulled_id = fields.Many2one('res.partner', string='Partner Annulled')