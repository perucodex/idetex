# -*- coding: utf-8 -*-
from odoo import models, fields, api

class BtnInicioFaseWizard(models.TransientModel):
    _name = 'btn.inicio.fase.wizard'
    _description = 'Wizard Inicio Proceso Manufactura'

    line_id = fields.Many2one(
        'control.proceso.lines',
        string="Línea de Proceso",
        required=True
    )

    fecha_inicio = fields.Datetime(
        string="Fecha y Hora de Inicio",
        default=lambda self: fields.Datetime.now(),
        required=True
    )

    def action_confirmar(self):
        self.ensure_one()
        self.line_id.action_start(fecha_inicio=self.fecha_inicio)
        return {'type': 'ir.actions.act_window_close'}
