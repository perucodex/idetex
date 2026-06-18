# -*- coding: utf-8 -*-
from odoo import models, fields


class MachineLayout(models.Model):
    _name = 'idtx.machine.layout'
    _description = 'Machine Grid Layout Position'

    equipment_id = fields.Many2one(
        'maintenance.equipment', required=True, ondelete='cascade', index=True
    )
    area = fields.Char(required=True, index=True)
    slot_index = fields.Integer(default=0)

    _sql_constraints = [
        ('unique_equipment_area', 'unique(equipment_id, area)',
         'Una máquina solo puede tener una posición por área.'),
    ]
