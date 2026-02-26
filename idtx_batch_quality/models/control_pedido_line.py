from odoo import models, fields, api
from odoo.exceptions import UserError


class ControlPedidoLine(models.Model):
    _inherit = "control.pedido.line"

    # -----------------------------
    # TONO (existente)
    # -----------------------------
    tono_eval_log_ids = fields.One2many(
        "control.tono.eval.log",
        "pedido_line_id",
        string="Evaluaciones",
    )

    can_eval_tono = fields.Boolean(
        string="Puede evaluar tono tacho",
        compute="_compute_can_eval_tono",
        store=False,
    )
    can_eval_tono_acabado = fields.Boolean(
        string="Puede evaluar tono acabado",
        compute="_compute_can_eval_tono_acabado",
        store=False,
    )
    end_tono = fields.Boolean(
        string="Tono Finalizado",
        compute="_compute_end_tono",
        store=False,
    )
    has_tono_eval_logs = fields.Boolean(
        string="Tiene evaluaciones",
        compute="_compute_has_tono_eval_logs",
        store=False,
    )

    @api.depends("tono_eval_log_ids")
    def _compute_has_tono_eval_logs(self):
        for rec in self:
            rec.has_tono_eval_logs = bool(rec.tono_eval_log_ids)

    @api.depends(
        "tono_eval_log_ids.tono",
        "tono_eval_log_ids.resultado",
        "proceso_ids.fasCod",
        "proceso_ids.barFasDTI",
        "proceso_ids.barFasDTF",
    )
    def _compute_can_eval_tono(self):
        for rec in self:
            procesos_tenido = rec.proceso_ids.filtered(
                lambda p: "TEÑIDO" in ((p.fasCod or "").strip().upper())
            )
            tiene_tenido_cerrado = any(p.barFasDTI and p.barFasDTF for p in procesos_tenido)

            if not tiene_tenido_cerrado:
                rec.can_eval_tono = False
                continue

            logs_tacho = rec.tono_eval_log_ids.filtered(lambda l: l.tono == "tacho")
            tiene_tacho_ok = any(l.resultado in ("aprobado", "concesionado") for l in logs_tacho)
            rec.can_eval_tono = not tiene_tacho_ok

    @api.depends("tono_eval_log_ids.tono", "tono_eval_log_ids.resultado")
    def _compute_can_eval_tono_acabado(self):
        for rec in self:
            logs_tacho = rec.tono_eval_log_ids.filtered(lambda l: l.tono == "tacho")
            logs_acabado = rec.tono_eval_log_ids.filtered(lambda l: l.tono == "acabado")

            tiene_tacho_ok = any(l.resultado in ("aprobado", "concesionado") for l in logs_tacho)
            tiene_acabado_final = any(l.resultado in ("aprobado", "concesionado") for l in logs_acabado)
            rec.can_eval_tono_acabado = tiene_tacho_ok and not tiene_acabado_final

    @api.depends("tono_eval_log_ids.tono", "tono_eval_log_ids.resultado")
    def _compute_end_tono(self):
        for rec in self:
            resultados = set(
                rec.tono_eval_log_ids.filtered(lambda l: l.tono == "acabado").mapped("resultado")
            )
            rec.end_tono = bool(resultados.intersection({"aprobado", "concesionado"}))

    def action_evaluar_tono(self):
        self.ensure_one()
        if not self.can_eval_tono:
            raise UserError(
                "La evaluación de Tono Tacho solo está disponible cuando el proceso TEÑIDO tenga inicio y fin, "
                "y mientras no exista un Tacho aprobado o concesionado."
            )

        return {
            "type": "ir.actions.act_window",
            "name": "Evaluar Tono Tacho",
            "res_model": "control.tono.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_pedido_line_id": self.id},
        }

    def action_evaluar_tono_acabado(self):
        self.ensure_one()
        if not self.can_eval_tono_acabado:
            raise UserError(
                "La evaluación de Tono Acabado solo está disponible después de aprobar o concesionar Tono Tacho, "
                "y mientras no exista un cierre final de Acabado."
            )

        return {
            "type": "ir.actions.act_window",
            "name": "Evaluar Tono Acabado",
            "res_model": "control.tono.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_pedido_line_id": self.id, "tono_acabado": True},
        }

    # -----------------------------
    # APARIENCIA (nuevo)
    # -----------------------------
    apariencia_line_ids = fields.One2many(
        "control.apariencia.line",
        "pedido_line_id",
        string="Apariencia",
    )

    has_apariencia_lines = fields.Boolean(
        string="Tiene líneas de apariencia",
        compute="_compute_has_apariencia_lines",
        store=False,
    )

    can_apariencia = fields.Boolean(
        string="Puede registrar apariencia",
        compute="_compute_can_apariencia",
        store=False,
    )

    @api.depends("apariencia_line_ids")
    def _compute_has_apariencia_lines(self):
        for rec in self:
            rec.has_apariencia_lines = bool(rec.apariencia_line_ids)

    @api.depends("tono_eval_log_ids.tono", "tono_eval_log_ids.resultado")
    def _compute_can_apariencia(self):
        """
        Apariencia disponible cuando:
        - exista Tacho (aprobado o concesionado)
        - y exista Acabado (aprobado o concesionado)
        """
        for rec in self:
            logs = rec.tono_eval_log_ids
            tacho_ok = any(
                l.tono == "tacho" and l.resultado in ("aprobado", "concesionado")
                for l in logs
            )
            acabado_ok = any(
                l.tono == "acabado" and l.resultado in ("aprobado", "concesionado")
                for l in logs
            )
            rec.can_apariencia = bool(tacho_ok and acabado_ok)

    def action_apariencia(self):
        self.ensure_one()
        if not self.can_apariencia:
            raise UserError(
                "Apariencia solo está disponible cuando existan evaluaciones finales de Tono Tacho "
                "y Tono Acabado (Aprobado o Concesionado)."
            )

        return {
            "type": "ir.actions.act_window",
            "name": "Registrar Apariencia",
            "res_model": "control.apariencia.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_pedido_line_id": self.id},
        }