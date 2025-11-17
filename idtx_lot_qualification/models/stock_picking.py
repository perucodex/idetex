# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
from odoo import fields, models


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    def button_validate(self):
        picking = super().button_validate()
        for line in self.move_ids.move_line_ids:
            if line.product_id.is_thread:
                
                line.lot_id.lot_detail_ids.create
        return picking