# -*- coding: utf-8 -*-

from odoo import api, fields, models


class ProductAnalysis(models.Model):
    _inherit = 'product.analysis'

    # Última actualización del precio de tejido del análisis (fuente del precio
    # de la fase de TEJIDO en la cotización). Se estampa sola al crear/escribir
    # weaving_price o su moneda; el write_date del análisis no sirve porque
    # cambia por cualquier dato técnico. La muestra el widget de fechas de
    # precio de los procesos del vendedor (JP, 23-sep-2026).
    weaving_price_date = fields.Datetime(
        'Fecha de precio de tejido', readonly=True, copy=False,
        help='Última actualización del precio de tejido del análisis.')

    @api.model_create_multi
    def create(self, vals_list):
        now = fields.Datetime.now()
        for vals in vals_list:
            if vals.get('weaving_price'):
                vals.setdefault('weaving_price_date', now)
        return super().create(vals_list)

    def write(self, vals):
        if 'weaving_price_date' not in vals and ('weaving_price' in vals or 'currency_id' in vals):
            vals = dict(vals, weaving_price_date=fields.Datetime.now())
        return super().write(vals)
