from odoo import api, models


class PosSession(models.Model):
    _inherit = 'pos.session'

    @api.model
    def _load_pos_data_models(self, config):
        models_list = super()._load_pos_data_models(config)
        models_list.append('account.payment.term')
        return models_list
