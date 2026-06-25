# -*- coding: utf-8 -*-
from odoo import models, fields, api


class StockLocation(models.Model):
    _inherit = 'stock.location'


class StockMoveLine(models.Model):
    _inherit = 'stock.move.line'

    thread_bag_qty    = fields.Integer(string='Bolsas', default=0)
    thread_cone_qty   = fields.Integer(string='Conos/Bolsa', default=0)
    thread_cone_weight = fields.Float(string='Peso Cono (kg)', digits=(12, 4), default=0.0)
    thread_total_cones = fields.Integer(
        compute='_compute_thread_totals',
        string='Total Conos',
    )

    def _compute_thread_totals(self):
        for rec in self:
            rec.thread_total_cones = rec.thread_bag_qty * rec.thread_cone_qty


class StockMove(models.Model):
    _inherit = 'stock.move'

    # thread_is_thread se define en stock_move.py como related a
    # product_id.is_thread (store=True). Aquí estaba duplicado con un
    # default=False redundante sobre un campo related — se eliminó.
    thread_control_generated = fields.Boolean(string='Control Generado', default=False)


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    thread_liquidation_production_id = fields.Many2one(
        'mrp.production',
        string='Orden de Producción (Liquidación)',
        index=True,
    )
