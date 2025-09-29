# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models

class ResUsers(models.Model):
    _inherit = 'res.users'

    signature_image = fields.Image(string="Signature",copy=False, attachment=True, max_width=1024, max_height=1024)

