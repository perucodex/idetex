from odoo import fields, models


class ControlAparienciaDefecto(models.Model):
    _inherit = "control.apariencia.defecto"
    
    type_deffect = fields.Selection([
        ('quality', 'Quality'),
        ('printing', 'Printing'),
    ], string='Deffect Type', default='quality', required=True)
    type_printing = fields.Selection([
        ('digital', 'Digital'),
        ('rotary', 'Rotary'),
        ('both', 'Both'),
    ], string='Printing Type', default='digital')