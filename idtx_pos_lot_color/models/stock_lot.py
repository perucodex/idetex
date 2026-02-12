# Part of Odoo. See LICENSE file for full copyright and licensing details.
from odoo import models, api

class StockLot(models.Model):
    _name = "stock.lot"
    _inherit = ["stock.lot", "pos.load.mixin"]

    @api.model
    def _load_pos_data_fields(self, config):
        res = super()._load_pos_data_fields(config)
        res += ['name','product_id','color_code','color_name']
        return res
