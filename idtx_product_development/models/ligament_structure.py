from odoo import models, fields
from odoo.exceptions import UserError


class LigamentStructure(models.Model):
    _name = 'ligament.structure'
    _description = 'Ligament Base Structure'
    _order = 'name'

    name = fields.Char('Name', required=True)
    active = fields.Boolean(default=True)
    notes = fields.Text('Notes')
    # Mismos nombres de campo que product.analysis para poder reutilizar
    # grid_ligament_widget sin cambios (el widget lee estos campos del record).
    ligament_row = fields.Integer('Rows', default=0)
    ligament_column = fields.Integer('Columns', default=0)
    ligament_join_row_column = fields.Char('Union')
    grid_data = fields.Text(string='Data Widget')

    _name_unique = models.Constraint(
        'unique(name)',
        'Structure name must be unique!',
    )

    def action_generate(self):
        row = self.ligament_row
        column = self.ligament_column
        if not row or row <= 0:
            raise UserError('Row number must be greater than 0')
        if not column or column <= 0:
            raise UserError('Column number must be greater than 0')
        self.ligament_join_row_column = '%s, %s' % (row, column)
        self.grid_data = ''
