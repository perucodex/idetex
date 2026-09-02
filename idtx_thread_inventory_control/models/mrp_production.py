# -*- coding: utf-8 -*-
from odoo import _, api, fields, models


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

    thread_waste_qty = fields.Float(
        'Merma de Hilo (kg)', compute='_compute_thread_waste', digits=(16, 2),
        help='Kilos de hilo desechados en esta orden: lo que no volvió en bolsas '
             'ni se hizo tela al cerrar el tejido.')
    thread_waste_count = fields.Integer(compute='_compute_thread_waste')

    def _compute_thread_waste(self):
        datos = self.env['stock.scrap']._read_group(
            [('production_id', 'in', self.ids), ('state', '=', 'done'),
             ('product_id.product_tmpl_id.is_thread', '=', True)],
            ['production_id'], ['scrap_qty:sum', '__count'])
        por_of = {of.id: (kg, n) for of, kg, n in datos}
        for rec in self:
            kg, n = por_of.get(rec.id, (0.0, 0))
            rec.thread_waste_qty = kg
            rec.thread_waste_count = n

    def action_view_thread_waste(self):
        """Los desechos de hilo de esta orden."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Merma de hilo de %s', self.name),
            'res_model': 'stock.scrap',
            'view_mode': 'list,form',
            'domain': [('production_id', '=', self.id), ('state', '=', 'done'),
                       ('product_id.product_tmpl_id.is_thread', '=', True)],
        }

    def _compute_thread_liquidation_count(self):
        for rec in self:
            rec.thread_liquidation_count = len(rec.thread_liquidation_picking_ids)

    def _compute_thread_liquidation_pending_qty(self):
        for rec in self:
            rec.thread_liquidation_pending_qty = 0.0
