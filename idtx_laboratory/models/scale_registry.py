# -*- coding: utf-8 -*-
from odoo import models, fields

class ScaleRegistry(models.Model):
    _name = "scale.registry"
    _description = "Registro de Balanza"

    name = fields.Char(string="Nombre de la balanza", required=True)
    ip = fields.Char(string="IP de la balanza", required=True)
