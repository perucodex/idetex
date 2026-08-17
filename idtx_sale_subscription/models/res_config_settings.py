# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    idtx_subscription_period_format = fields.Selection(
        related='company_id.idtx_subscription_period_format',
        readonly=False)
