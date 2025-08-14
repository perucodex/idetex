# -*- coding: utf-8 -*-

from odoo import fields, models

import requests

class MaintenanceEquipment(models.Model):
    _inherit = 'maintenance.equipment'
    
    gauge_id = fields.Many2one('product.gauge', string='Equipment Type')
    equipment_ip = fields.Char('Equipment IP')
    user = fields.Char('User')
    password = fields.Char('Password')
    state = fields.Selection([
        ('con', 'Connected'),
        ('not', 'Not connected'),
    ], string='State', default='not')
    impresora_dashboard_dummy = fields.Char(string="Dashboard Impresora", compute="_compute_impresora_dashboard")

    def _compute_impresora_dashboard(self):
        for rec in self:
            rec.impresora_dashboard_dummy = ""

    def connect(self):
        try:
            bridge_url = f"http://{self.equipment_ip}:5000/impresorajpk"
            auth = None
            if self.user and self.password:
                auth = (self.user, self.password)
            r = requests.get(bridge_url, timeout=5, auth=auth)
            r.raise_for_status()
            self.state = 'con'
        except Exception as e:
            self.state = 'not'

    def disconnect(self):
        self.state = 'not'