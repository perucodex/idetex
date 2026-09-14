# -*- coding: utf-8 -*-
from odoo import fields, models


class StockLot(models.Model):
    _inherit = 'stock.lot'

    quality_grade = fields.Selection(
        related='roll_id.quality_grade', string='Grado', store=True, index=True)
    quality_state = fields.Selection(
        related='roll_id.quality_state', string='Estado calidad', store=True)


class StockQuant(models.Model):
    _inherit = 'stock.quant'

    quality_grade = fields.Selection(
        related='lot_id.quality_grade', string='Grado', store=True, index=True)
