# -*- coding: utf-8 -*-
from odoo import models, fields, api


class StockLot(models.Model):
    _inherit = 'stock.lot'

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
