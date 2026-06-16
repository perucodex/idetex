# -*- coding: utf-8 -*-
from odoo import fields, models


class VacacionalSeed(models.Model):
    _name = 'idtx.hr.vacacional.seed'
    _description = 'Histórico de variables vacacionales (seed de implementación)'
    _order = 'employee_id, period desc'

    employee_id = fields.Many2one(
        'hr.employee', string='Empleado', required=True,
        ondelete='cascade', index=True)
    period = fields.Date(
        string='Mes', required=True,
        help="Mes del histórico (cualquier día de ese mes). Se usa para los "
             "meses de la ventana de 6 que aún no tienen boleta en el sistema.")
    amount = fields.Monetary(
        string='Variables del mes', currency_field='currency_id',
        help="Suma de HE 25% + HE 35% + bonificación nocturna + prima textil "
             "de ese mes, tomada del sistema anterior.")
    currency_id = fields.Many2one(
        related='employee_id.company_id.currency_id', readonly=True)

    _uniq_emp_period = models.Constraint(
        'unique(employee_id, period)',
        'Ya existe un registro de variables para ese empleado y esa fecha.',
    )
