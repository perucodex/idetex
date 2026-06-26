# -*- coding: utf-8 -*-
from odoo import _, models, fields, api


class StockLot(models.Model):
    _inherit = 'stock.lot'

    # --- Controles de hilo (thread.lot.control) ---
    thread_control_ids = fields.One2many(
        'thread.lot.control', 'lot_id',
        string='Controles de Hilo',
    )
    thread_control_count = fields.Integer(
        compute='_compute_thread_control_count',
        string='# Controles',
    )
    thread_in_bags      = fields.Integer(compute='_compute_thread_balances', string='Bolsas Entrada')
    thread_in_cones     = fields.Integer(compute='_compute_thread_balances', string='Conos Entrada')
    thread_in_weight    = fields.Float(compute='_compute_thread_balances',   string='Kg Entrada')
    thread_out_bags     = fields.Integer(compute='_compute_thread_balances', string='Bolsas Salida')
    thread_out_cones    = fields.Integer(compute='_compute_thread_balances', string='Conos Salida')
    thread_out_weight   = fields.Float(compute='_compute_thread_balances',   string='Kg Salida')
    thread_balance_bags   = fields.Integer(compute='_compute_thread_balances', string='Saldo Bolsas')
    thread_balance_cones  = fields.Integer(compute='_compute_thread_balances', string='Saldo Conos')
    thread_balance_weight = fields.Float(compute='_compute_thread_balances',   string='Saldo Kg')
    thread_second_quality_bags   = fields.Integer(compute='_compute_thread_balances', string='2da Cal. Bolsas')
    thread_second_quality_cones  = fields.Integer(compute='_compute_thread_balances', string='2da Cal. Conos')
    thread_second_quality_weight = fields.Float(compute='_compute_thread_balances',   string='2da Cal. Kg')

    # --- Bolsas de hilo (thread.bag) ---
    thread_bag_ids = fields.One2many("thread.bag", "lot_id", string="Bolsas de Hilo")
    thread_bag_count = fields.Integer(
        string="Bolsas Disponibles", compute="_compute_thread_totals",
    )
    thread_available_net = fields.Float(
        string="Kg Disponibles", compute="_compute_thread_totals", digits=(16, 3),
    )
    thread_cone_count = fields.Integer(
        string="Conos Disponibles", compute="_compute_thread_totals",
    )

    def _compute_thread_control_count(self):
        for rec in self:
            rec.thread_control_count = len(rec.thread_control_ids)

    def _compute_thread_balances(self):
        for rec in self:
            rec.thread_in_bags = rec.thread_in_cones = 0
            rec.thread_in_weight = 0.0
            rec.thread_out_bags = rec.thread_out_cones = 0
            rec.thread_out_weight = 0.0
            rec.thread_balance_bags = rec.thread_balance_cones = 0
            rec.thread_balance_weight = 0.0
            rec.thread_second_quality_bags = rec.thread_second_quality_cones = 0
            rec.thread_second_quality_weight = 0.0

    @api.depends("thread_bag_ids.state", "thread_bag_ids.net_weight", "thread_bag_ids.cone_qty")
    def _compute_thread_totals(self):
        for lot in self:
            avail = lot.thread_bag_ids.filtered(lambda b: b.state == "available")
            lot.thread_bag_count = len(avail)
            lot.thread_available_net = sum(avail.mapped("net_weight"))
            lot.thread_cone_count = sum(avail.mapped("cone_qty"))

    def action_view_thread_bags(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Bolsas de %s") % self.name,
            "res_model": "thread.bag",
            "view_mode": "list,form",
            "domain": [("lot_id", "=", self.id)],
            "context": {"default_lot_id": self.id, "default_product_id": self.product_id.id},
        }
