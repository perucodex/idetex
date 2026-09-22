# -*- coding: utf-8 -*-
from odoo import fields, models


class MrpProductionRoll(models.Model):
    """Enlace del rollo pesado con la marca de separación que puso Calidad
    antes del pesado (qc.roll.hold). Los campos de grado/observación viven
    en idtx_mrp (se deciden al pesar)."""
    _inherit = 'mrp.production.roll'

    hold_id = fields.Many2one(
        'qc.roll.hold', string='Marca de calidad', readonly=True, copy=False,
        help='Marca "separar para reproceso" registrada por Calidad antes del pesado.')
