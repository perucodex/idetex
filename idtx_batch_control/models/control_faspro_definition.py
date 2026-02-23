# -*- coding: utf-8 -*-
from odoo import models, fields, api

class ControlFasproDefinition(models.Model):
    _name = "control.faspro.definition"
    _description = "Definicion de Procesos FASPRO"
    _rec_names_search = ['code', 'name']

    code = fields.Char("Código", required=True, index=True)
    name = fields.Char("Nombre")
    default_maq_code = fields.Char("Máquina por Defecto")

    def _compute_display_name(self):
        for rec in self:
            rec.display_name = f"[{rec.code}] {rec.name or ''}"
