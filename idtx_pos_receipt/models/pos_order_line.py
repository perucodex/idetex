# -*- coding: utf-8 -*-
from odoo import api, fields, models

class PosOrderLine(models.Model):
    _inherit = 'pos.order.line'

    lot_color_name = fields.Char("Lot Color", compute='_compute_lot_color_name')

    @api.depends('pack_lot_ids.lot_name')
    def _compute_lot_color_name(self):
        for line in self:
            if line.pack_lot_ids:
                # Buscamos el lote por nombre
                lot = self.env['stock.lot'].search([
                    ('name', '=', line.pack_lot_ids[0].lot_name),
                    ('product_id', '=', line.product_id.id),
                ], limit=1)
                if lot.color_code and lot.color_name:
                    line.lot_color_name = ('[' + lot.color_code + '] ' + lot.color_name) or ''
                else:
                    line.lot_color_name = ''
            else:
                line.lot_color_name = ''

    @api.model
    def _load_pos_data_fields(self, config):
        return super()._load_pos_data_fields(config) + ['lot_color_name']