# -*- coding: utf-8 -*-
from odoo import models, fields

class ScaleRegistry(models.Model):
    _name = "scale.registry"
    _description = "Scale Registry"

    name = fields.Char(string="Name", required=True)
    ip = fields.Char(string="Scale IP", required=True)
