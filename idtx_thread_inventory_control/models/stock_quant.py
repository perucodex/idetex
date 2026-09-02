# -*- coding: utf-8 -*-
"""Botón "Bolsas" en Existencias: del kilo del lote a las bolsas físicas."""

from odoo import _, api, fields, models


class StockQuant(models.Model):
    _inherit = 'stock.quant'

    thread_is_thread = fields.Boolean(
        'Es Hilo', related='product_id.product_tmpl_id.is_thread')
    thread_bag_count = fields.Integer(
        'Bolsas', compute='_compute_thread_bag_count',
        help='Bolsas registradas de este lote en esta ubicación.')

    @api.depends('product_id', 'lot_id', 'location_id')
    def _compute_thread_bag_count(self):
        hilo = self.filtered(lambda q: q.thread_is_thread and q.lot_id)
        (self - hilo).thread_bag_count = 0
        if not hilo:
            return
        datos = self.env['thread.bag']._read_group(
            [('lot_id', 'in', hilo.lot_id.ids),
             ('location_id', 'in', hilo.location_id.ids)],
            ['lot_id', 'location_id'], ['__count'])
        conteo = {(lote.id, ubic.id): n for lote, ubic, n in datos}
        for quant in hilo:
            quant.thread_bag_count = conteo.get(
                (quant.lot_id.id, quant.location_id.id), 0)

    def action_view_thread_bags(self):
        """Abre las bolsas de ESTE lote en ESTA ubicación."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Bolsas de %(lote)s en %(ubic)s',
                      lote=self.lot_id.name or self.product_id.display_name,
                      ubic=self.location_id.complete_name),
            'res_model': 'thread.bag',
            'view_mode': 'list,form',
            'domain': [
                ('lot_id', '=', self.lot_id.id),
                ('location_id', '=', self.location_id.id),
            ],
            'context': {
                'default_product_id': self.product_id.id,
                'default_lot_id': self.lot_id.id,
                'default_location_id': self.location_id.id,
                'search_default_group_state': 1,
            },
        }
