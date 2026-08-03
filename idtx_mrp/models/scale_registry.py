# -*- coding: utf-8 -*-
from odoo import models, fields

class ScaleRegistry(models.Model):
    _name = "scale.registry"
    _description = "Scale Registry"
    _rec_name = 'equipment_id'

    equipment_id = fields.Many2one('maintenance.equipment', string='Equipment', required=True)
    read_mode = fields.Selection([
        ('ip', 'Por IP (servidor)'),
        ('serial', 'Puerto COM (navegador)'),
    ], string='Modo de Lectura', default='ip', required=True,
        help="Por IP: un servidor local (balanza.py) lee el puerto serie y "
             "expone el peso por HTTP. Puerto COM (navegador): el navegador lee "
             "el puerto serie directamente con Web Serial (solo Chrome/Edge de "
             "escritorio); no requiere el script balanza.py.")
    ip = fields.Char(string="Scale IP",
        help="IP del servidor balanza.py (solo modo Por IP).")
    serial_baudrate = fields.Integer(string="Baudios (COM)", default=9600,
        help="Velocidad del puerto serie en modo Puerto COM. Normalmente 9600.")
    printer_id = fields.Many2one('maintenance.equipment', string='Printer', required=True)
    printer_ip = fields.Char(string="Printer IP", required=True)
