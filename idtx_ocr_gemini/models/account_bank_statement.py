from odoo import api, models

from .extract_mixin import PROMPT_BANK_STATEMENT, gemini_bank_statement_to_iap


class AccountBankStatement(models.Model):
    _inherit = 'account.bank.statement'

    @api.model
    def _contact_iap_extract(self, pathinfo, params):
        if pathinfo == 'parse':
            return self._idtx_gemini_run(
                params, PROMPT_BANK_STATEMENT, gemini_bank_statement_to_iap,
            )
        if pathinfo == 'get_result':
            return self._idtx_gemini_get_result(params)
        if pathinfo == 'validate':
            return {'status': 'success'}
        return {'status': 'error_internal'}
