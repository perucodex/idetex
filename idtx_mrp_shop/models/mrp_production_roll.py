# -*- coding: utf-8 -*-
from odoo import fields, models


class MrpProductionRoll(models.Model):
    _inherit = 'mrp.production.roll'

    release_picking_id = fields.Many2one(
        'stock.picking', string='Recepción de almacén', readonly=True, copy=False,
        ondelete='set null',
        help='Traslado interno Pesado → destino por grado con el que almacén recibe el rollo.')
    release_picking_state = fields.Selection(
        related='release_picking_id.state', string='Estado recepción')

    def action_view_release_picking(self):
        self.ensure_one()
        if not self.release_picking_id:
            return False
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'stock.picking',
            'view_mode': 'form',
            'res_id': self.release_picking_id.id,
        }
