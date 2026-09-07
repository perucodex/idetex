
from odoo import models, fields

# Ancho de codificación de la cuadrícula: slot_index = fila*GRID_COLS+columna.
# Debe coincidir EXACTO con GRID_COLS en static/src/machine_floor/machine_floor.js
# (el ancho visible ahí crece dinámicamente, pero esta es la base fija de
# codificación). Única fuente de verdad del lado Python — hooks.py y el
# controller (dashboard_alpha.py) importan esta constante en vez de tener
# cada uno su propio número, para no volver a desincronizarse.
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
