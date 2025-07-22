# -*- coding: utf-8 -*-

from odoo import api, fields, models, tools


class MaintenanceEquipment(models.Model):
    _inherit = 'maintenance.equipment'

    needles = fields.Integer('Needles')
    gauge_id = fields.Many2one('product.gauge', string='Gauge')
    diameter = fields.Integer('Diameter')
    feeders = fields.Integer('Feeders')