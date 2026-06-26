# -*- coding: utf-8 -*-

from odoo import fields, models

class MaintenanceEquipment(models.Model):
    _inherit = 'maintenance.equipment'

    code = fields.Char('Code')
    capacity_power = fields.Char('Capacity / Power')
    manufacture_year = fields.Char('Manufacture Year')
    enabled = fields.Boolean('Enabled')
    oos = fields.Boolean('Out of Service')

    # Datos para estimar el tiempo de tejido (máquinas circulares)
    rpm = fields.Float(
        'RPM', help="Velocidad de la máquina de tejido: revoluciones por minuto del cilindro.")
    efficiency = fields.Float(
        'Eficiencia (%)',
        help="Eficiencia de la máquina (0-100). Si es 0 se usa la eficiencia por "
             "defecto de la configuración de manufactura.")

    machine_state = fields.Selection([
        ('operativa',     'Operativa'),
        ('ejecutando',    'Ejecutando'),
        ('malograda',     'Malograda'),
        ('mantenimiento', 'Mantenimiento'),
        ('apagada',       'Apagada'),
    ], string='Estado de Máquina', default='apagada', index=True)
