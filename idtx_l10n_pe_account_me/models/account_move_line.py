from odoo import models


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    def _compute_account_id(self):
        super()._compute_account_id()
        for line in self.filtered(lambda l: l.display_type == 'payment_term'):
            move = line.move_id
            if not move.currency_id or move.currency_id == move.company_currency_id:
                continue
            partner = move.with_company(move.company_id).commercial_partner_id
            if move.is_sale_document(include_receipts=True):
                account = partner.property_account_receivable_me_id
            else:
                account = partner.property_account_payable_me_id
            if account:
                line.account_id = move.fiscal_position_id.map_account(account)
