# -*- coding: utf-8 -*-

from odoo import api, fields, models, tools


class MaintenanceEquipment(models.Model):
    _inherit = 'maintenance.equipment'
    
    gauge_id = fields.Many2one('product.gauge', string='Equipment Type')
