# -*- coding: utf-8 -*-
from odoo import models, fields

class ScaleRegistry(models.Model):
    _name = "scale.registry"
    _description = "Scale Registry"
    _rec_name = 'equipment_id'

    equipment_id = fields.Many2one('maintenance.equipment', string='Equipment', required=True)
    ip = fields.Char(string="Scale IP", required=True)
    printer_id = fields.Many2one('maintenance.equipment', string='Printer', required=True)
    printer_ip = fields.Char(string="Printer IP", required=True)
