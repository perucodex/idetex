# -*- coding: utf-8 -*-
from odoo import models, fields, api
import pytz

class BtnInicioFaseWizard(models.TransientModel):
    _name = 'btn.inicio.fase.wizard'
    _description = 'Wizard Inicio Proceso Manufactura'

    line_id = fields.Many2one(
        'control.proceso.lines',
        string="Línea de Proceso",
        required=True
    )

    operator_code = fields.Char(
        string="Código de Operario",
        required=True
    )

    operator_name = fields.Char(
        string="Nombre de Operario",
        readonly=True
    )

    fecha_inicio = fields.Datetime(
        string="Fecha y Hora de Inicio",
        default=lambda self: fields.Datetime.now(),
        readonly=True,
        required=True
    )

    @api.onchange('operator_code')
    def _onchange_operator_code(self):
        if not self.operator_code:
            self.operator_name = False
            return

        # Consulta directa a SQL Server para validar operario
        conn = self.line_id.pedido_line_id.pedido_id._get_sql_connection()
        try:
            cursor = conn.cursor()
            # Buscamos en la tabla OPERAR por OpeCod
            query = "SELECT OpeNom FROM OPERAR WHERE OpeCod = ?"
            cursor.execute(query, self.operator_code)
            row = cursor.fetchone()
            
            if row:
                self.operator_name = row[0]
            else:
                self.operator_name = "OPERARIO NO ENCONTRADO"
        except Exception:
            self.operator_name = "ERROR DE CONEXIÓN"
        finally:
            conn.close()

    def action_confirmar(self):
        self.ensure_one()
        if not self.operator_name or self.operator_name in ["OPERARIO NO ENCONTRADO", "ERROR DE CONEXIÓN"]:
            from odoo.exceptions import UserError
            raise UserError("Por favor, ingrese un código de operario válido.")
            

        fecha_utc = self.fecha_inicio
        if fecha_utc.tzinfo is None:
            fecha_utc = pytz.utc.localize(fecha_utc)
        tz_peru = pytz.timezone(self.env.user.tz)
        fecha_peru = fecha_utc.astimezone(tz_peru)

        self.line_id.action_start(
            self.fecha_inicio,
            fecha_peru,
            self.operator_name
        )
        return
