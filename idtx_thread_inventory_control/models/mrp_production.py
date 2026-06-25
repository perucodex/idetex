# -*- coding: utf-8 -*-
from odoo import models, fields, api


class MrpProduction(models.Model):
    _inherit = 'mrp.production'

    thread_liquidation_picking_ids = fields.One2many(
        'stock.picking', 'thread_liquidation_production_id',
        string='Liquidaciones de Hilo',
    )
    thread_liquidation_count = fields.Integer(
        compute='_compute_thread_liquidation_count',
        string='# Liquidaciones',
    )
    thread_liquidation_pending_qty = fields.Float(
        compute='_compute_thread_liquidation_pending_qty',
        string='Kg Hilo Pendiente',
    )

    def _compute_thread_liquidation_count(self):
        for rec in self:
            rec.thread_liquidation_count = len(rec.thread_liquidation_picking_ids)

    def _compute_thread_liquidation_pending_qty(self):
        for rec in self:
            rec.thread_liquidation_pending_qty = 0.0
