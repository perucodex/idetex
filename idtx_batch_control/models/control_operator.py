# -*- coding: utf-8 -*-
from odoo import models, fields, api

class ControlOperator(models.Model):
    _name = "control.operator"
    _description = "Operarios de Planta"
    _rec_names_search = ['code', 'name']

    code = fields.Char("Código", required=True, index=True)
    name = fields.Char("Nombre", required=True)

    def _compute_display_name(self):
        for rec in self:
            rec.display_name = f"[{rec.code}] {rec.name}"
