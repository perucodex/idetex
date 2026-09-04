from odoo import api, models


class MailComposeMessage(models.TransientModel):
    _inherit = "mail.compose.message"

    @api.onchange("partner_ids")
    def _onchange_partner_ids_set_lang_for_lab_summary(self):
        # Keep stock compose behavior (same approach as sale) to avoid language-forced
        # stale template translations from overriding current HTML body.
        return
