# -*- coding: utf-8 -*-
"""Extensión de la sub-receta por lote con su uso en el Taller.

Vive aquí (y no en idtx_laboratory) porque `recipe_lot_id` en la partida y
`batch.registry` son modelos/campos de este módulo — laboratorio no puede
declarar un One2many hacia un campo que aún no existe en su cadena de
dependencias.
"""

from odoo import _, fields, models


class ColorRecipeLot(models.Model):
    _inherit = 'color.recipe.lot'

    # Partidas del Taller que tiñen con esta sub-receta.
    batch_ids = fields.One2many(
        'mrp.workorder.batch', 'recipe_lot_id', string='Partidas')
    batch_count = fields.Integer(
        'Partidas', compute='_compute_batch_count')
    # Ya tiene teñidos registrados en el Taller (batch.registry de alguna
    # de sus partidas).
    has_batch_registry = fields.Boolean(
        'Con Registro de Operaciones', compute='_compute_has_batch_registry',
        search='_search_has_batch_registry')

    def _compute_batch_count(self):
        counts = dict(self.env['mrp.workorder.batch']._read_group(
            [('recipe_lot_id', 'in', self.ids)],
            groupby=['recipe_lot_id'], aggregates=['__count']))
        for rec in self:
            rec.batch_count = counts.get(rec, 0)

    def _compute_has_batch_registry(self):
        regs = self.env['batch.registry'].sudo().search(
            [('batch_id.recipe_lot_id', 'in', self.ids)])
        with_registry = set(regs.batch_id.recipe_lot_id.ids)
        for rec in self:
            rec.has_batch_registry = rec.id in with_registry

    def _search_has_batch_registry(self, operator, value):
        if operator in ('in', 'not in') and isinstance(value, (list, tuple, set)):
            want = (operator == 'in') == (True in set(value))
        elif operator in ('=', '!='):
            want = (operator == '=') == bool(value)
        else:
            raise NotImplementedError()
        regs = self.env['batch.registry'].sudo().search(
            [('batch_id.recipe_lot_id', '!=', False)])
        ids = regs.batch_id.recipe_lot_id.ids
        return [('id', 'in' if want else 'not in', ids)]

    def action_view_batches(self):
        self.ensure_one()
        return {
            'name': _('Partidas'),
            'type': 'ir.actions.act_window',
            'res_model': 'mrp.workorder.batch',
            'view_mode': 'list,form',
            'domain': [('recipe_lot_id', '=', self.id)],
        }
