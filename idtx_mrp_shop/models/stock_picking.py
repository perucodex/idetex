# -*- coding: utf-8 -*-
from odoo import api, fields, models


class StockPicking(models.Model):
    """Recepción de rollos terminados: traslado interno Pesado → destino por
    grado que valida el almacenero."""
    _inherit = 'stock.picking'

    roll_release_batch_id = fields.Many2one(
        'mrp.workorder.batch', string='Partida (recepción de rollos)', index=True,
        readonly=True, copy=False, ondelete='set null')
    roll_release_grade = fields.Selection(
        [('A', 'A · Existencias'), ('B', 'B · Saldo'), ('M', 'M · Mermas')],
        string='Grado recibido', readonly=True, copy=False)
    released_roll_ids = fields.One2many(
        'mrp.production.roll', 'release_picking_id', string='Rollos liberados', readonly=True)
    released_roll_count = fields.Integer(compute='_compute_released_roll_count')

    @api.depends('released_roll_ids')
    def _compute_released_roll_count(self):
        for picking in self:
            picking.released_roll_count = len(picking.released_roll_ids)

    def action_cancel(self):
        """Si almacén anula la recepción, los rollos vuelven a estar
        pendientes de liberar (siguen en la ubicación de pesado)."""
        res = super().action_cancel()
        for picking in self.filtered(lambda p: p.state == 'cancel' and p.released_roll_ids):
            picking.released_roll_ids.sudo().write({
                'quality_released': False,
                'quality_release_date': False,
                'release_picking_id': False,
            })
        return res
