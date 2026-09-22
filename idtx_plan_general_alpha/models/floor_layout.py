
from odoo import models, fields

GRID_COLS = 60


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
        'check(span_cols > 0)',
        'El ancho combinado debe ser de al menos 1 celda.',
    )
    _span_rows_valid = models.Constraint(
        'check(span_rows > 0)',
        'El alto combinado debe ser de al menos 1 celda.',
    )
