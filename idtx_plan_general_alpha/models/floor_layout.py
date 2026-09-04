
from odoo import models, fields


class AlphaFloorLayout(models.Model):
    _name = 'idtx.alpha.floor.layout'
    _description = 'Posición de máquina en cuadrícula por centro de trabajo'

    equipment_id = fields.Many2one(
        'maintenance.equipment', required=True, ondelete='cascade', index=True
    )
    workcenter = fields.Char(required=True, index=True)
    slot_index = fields.Integer(default=0)
    span_cols = fields.Integer(default=1)
    span_rows = fields.Integer(default=1)

    _unique_eq_wc = models.Constraint(
        'unique(equipment_id, workcenter)',
        'Una máquina solo puede ocupar una posición por centro de trabajo.',
    )
    _span_cols_valid = models.Constraint(
        'check(span_cols in (1, 2, 3, 4))',
        'El ancho combinado debe ser entre 1 y 4 celdas.',
    )
    _span_rows_valid = models.Constraint(
        'check(span_rows in (1, 2, 3, 4))',
        'El alto combinado debe ser entre 1 y 4 celdas.',
    )
