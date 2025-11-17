# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models

class ResCompany(models.Model):
    _inherit = 'res.company'
    
    l10n_pe_edi_provider = fields.Selection(
        selection_add=[
            ('efact', 'Efact'),
        ],
    )