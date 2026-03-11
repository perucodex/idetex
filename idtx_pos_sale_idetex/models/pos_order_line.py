# -*- coding: utf-8 -*-
from odoo import models, fields, api

class PosOrderLine(models.Model):
    _inherit = 'pos.order.line'

    color_name = fields.Char(string='Color Name', help='Nombre del color del rollo seleccionado')

    @api.model
    def _load_pos_data_fields(self, config):
        params = super()._load_pos_data_fields(config)
        params += ['color_name']
        return params
