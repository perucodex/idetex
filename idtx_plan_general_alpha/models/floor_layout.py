# -*- coding: utf-8 -*-
from odoo import models, fields


class AlphaFloorLayout(models.Model):
    _name = 'idtx.alpha.floor.layout'
    _description = 'Posición de máquina en cuadrícula por centro de trabajo'

    equipment_id = fields.Many2one(
        'maintenance.equipment', required=True, ondelete='cascade', index=True
    )
    workcenter = fields.Char(required=True, index=True)
    slot_index = fields.Integer(default=0)

    _unique_eq_wc = models.Constraint(
        'unique(equipment_id, workcenter)',
        'Una máquina solo puede ocupar una posición por centro de trabajo.',
    )
