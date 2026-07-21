from odoo import models, fields


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    l10n_pe_use_tareo = fields.Boolean(
        related='company_id.l10n_pe_use_tareo', readonly=False)
