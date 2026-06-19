# -*- coding: utf-8 -*-

from odoo import fields, models

class MaintenanceEquipment(models.Model):
    _inherit = 'maintenance.equipment'

    code = fields.Char('Code')
    capacity_power = fields.Char('Capacity / Power')
    manufacture_year = fields.Char('Manufacture Year')
    enabled = fields.Boolean('Enabled')
    oos = fields.Boolean('Out of Service')

    machine_state = fields.Selection([
        ('operativa',     'Operativa'),
        ('ejecutando',    'Ejecutando'),
        ('malograda',     'Malograda'),
        ('mantenimiento', 'Mantenimiento'),
        ('apagada',       'Apagada'),
    ], string='Estado de Máquina', default='apagada', index=True)
