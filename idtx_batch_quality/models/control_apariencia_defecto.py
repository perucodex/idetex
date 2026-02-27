from odoo import fields, models


class ControlAparienciaDefecto(models.Model):
    _name = "control.apariencia.defecto"
    _description = "Defectos Apariencia (Maestro)"
    _order = "name asc, id asc"

    name = fields.Char(string="Defecto", required=True, index=True)
    is_active = fields.Boolean(string="Activo", default=True)
    is_hueco = fields.Boolean(string="¿Es Hueco?", default=False)