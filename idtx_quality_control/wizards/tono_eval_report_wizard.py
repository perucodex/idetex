from datetime import datetime, time, timedelta

import pytz

from odoo import _, fields, models
from odoo.exceptions import UserError


class ControlTonoEvalReportWizard(models.TransientModel):
    _name = "qc.tone.eval.report.wizard"
    _description = "Imprimir Evaluación de Tono en Producción"

    date_from = fields.Datetime(
        string="Desde",
        required=True,
        default=lambda self: self._default_shift()[0],
    )
    date_to = fields.Datetime(
        string="Hasta",
        required=True,
        default=lambda self: self._default_shift()[1],
    )
    formato = fields.Selection(
        [("pdf", "PDF"), ("xlsx", "Excel")],
        string="Formato",
        required=True,
        default="pdf",
    )

    def _default_shift(self):
        """Turno día del día anterior (07:00 a 19:00) en la tz del usuario."""
        tz = pytz.timezone(self.env.user.tz or "America/Lima")
        ayer = fields.Date.context_today(self) - timedelta(days=1)
        inicio = tz.localize(datetime.combine(ayer, time(7, 0)))
        fin = tz.localize(datetime.combine(ayer, time(19, 0)))
        return (
            inicio.astimezone(pytz.utc).replace(tzinfo=None),
            fin.astimezone(pytz.utc).replace(tzinfo=None),
        )

    def action_next_shift(self):
        """Avanza al turno siguiente: +12 horas en ambos extremos."""
        self.ensure_one()
        self.write({
            "date_from": self.date_from + timedelta(hours=12),
            "date_to": self.date_to + timedelta(hours=12),
        })
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }

    def action_print(self):
        self.ensure_one()
        if self.date_to <= self.date_from:
            raise UserError(_("La fecha final debe ser posterior a la inicial."))
        logs = self.env["qc.tone.eval.log"].search([
            ("fecha_eval", ">=", self.date_from),
            ("fecha_eval", "<=", self.date_to),
            ("tono", "in", ["tacho", "acabado"]),
        ])
        if not logs:
            raise UserError(_("No hay evaluaciones de tono en el rango seleccionado."))
        if self.formato == "xlsx":
            return logs.action_export_tono_eval_xlsx()
        return self.env.ref(
            "idtx_quality_control.action_report_tono_eval_produccion"
        ).report_action(logs)
