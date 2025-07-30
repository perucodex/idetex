# -*- coding: utf-8 -*-

from odoo import api, fields, models, tools


class MaintenanceEquipment(models.Model):
    _inherit = 'maintenance.equipment'
    
    maintenance_equipment_type_id = fields.Many2one('maintenance.equipment.type', string='Equipment Type')

class MaintenanceEquipmentType(models.Model):
    _name = 'maintenance.equipment.type'
    _description = 'Maintenance Equipment Type'

    name = fields.Char('Name')
    needles = fields.Integer('Needles')
    gauge_id = fields.Many2one('product.gauge', string='Gauge')
    diameter = fields.Integer('Diameter')
    feeders = fields.Integer('Feeders')