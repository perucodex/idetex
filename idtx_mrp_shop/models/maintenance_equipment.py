# -*- coding: utf-8 -*-

from odoo import fields, models

class MaintenanceEquipment(models.Model):
    _inherit = 'maintenance.equipment'
    
    alkalis_vol = fields.Float('Alkalis Volume')
    color_vol = fields.Float('Color Volume')
    # alkalis_tanq_vol = fields.Float('Alkalis Tanq Volume')
    # color_tanq_vol = fields.Float('Color Tanq Volume')