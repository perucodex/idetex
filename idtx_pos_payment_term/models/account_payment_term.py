from odoo import api, models


class AccountPaymentTerm(models.Model):
    _name = 'account.payment.term'
    _inherit = ['account.payment.term', 'pos.load.mixin']

    @api.model
    def _load_pos_data_domain(self, data, config):
        return [
            ('active', '=', True),
            ('company_id', 'in', (False, config.company_id.id)),
        ]

    @api.model
    def _load_pos_data_fields(self, config):
        return ['id', 'name', 'display_name']
