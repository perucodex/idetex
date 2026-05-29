from odoo import api, models

from .extract_mixin import PROMPT_EXPENSE, gemini_expense_to_iap


class HrExpense(models.Model):
    _inherit = 'hr.expense'

    @api.model
    def _contact_iap_extract(self, pathinfo, params):
        if pathinfo == 'parse':
            return self._idtx_gemini_run(
                params, PROMPT_EXPENSE, gemini_expense_to_iap,
            )
        if pathinfo == 'get_result':
            return self._idtx_gemini_get_result(params)
        if pathinfo == 'validate':
            return {'status': 'success'}
        return {'status': 'error_internal'}
