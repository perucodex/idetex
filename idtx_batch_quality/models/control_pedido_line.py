from odoo import models, fields, api
from odoo.fields import Domain
from odoo.exceptions import UserError

class ControlPedidoLine(models.Model):
    _inherit = "control.pedido.line"

    tono_eval_log_ids = fields.One2many(
        "control.tono.eval.log",
        "pedido_line_id",
        string="Evaluaciones",
    )

    can_eval_tono = fields.Boolean(compute="_compute_can_eval_tono", store=False)
    can_eval_tono_acabado = fields.Boolean(compute="_compute_can_eval_tono_acabado", store=False)
    end_tono = fields.Boolean(compute="_compute_end_tono", store=False)
    has_tono_eval_logs = fields.Boolean(compute="_compute_has_tono_eval_logs", store=False)

    apariencia_line_ids = fields.One2many(
        "control.apariencia.line",
        "pedido_line_id",
        string="Apariencia",
    )
    apariencia_eval_ids = fields.One2many(
        "control.apariencia.eval",
        "pedido_line_id",
        string="Evaluaciones de Apariencia",
    )
    has_apariencia_lines = fields.Boolean(compute="_compute_has_apariencia_lines", store=False)
    can_apariencia = fields.Boolean(compute="_compute_can_apariencia", store=False)

    @api.depends("tono_eval_log_ids")
    def _compute_has_tono_eval_logs(self):
        for rec in self:
            rec.has_tono_eval_logs = bool(rec.tono_eval_log_ids)

    @api.depends("apariencia_line_ids", "apariencia_eval_ids.line_ids")
    def _compute_has_apariencia_lines(self):
        for rec in self:
            rec.has_apariencia_lines = bool(rec.apariencia_line_ids or rec.apariencia_eval_ids)

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

    @api.depends("tono_eval_log_ids.tono", "tono_eval_log_ids.resultado")
    def _compute_can_apariencia(self):
        for rec in self:
            logs = rec.tono_eval_log_ids
            tacho_ok = any(l.tono == "tacho" and l.resultado in ("aprobado", "concesionado") for l in logs)
            acabado_ok = any(l.tono == "acabado" and l.resultado in ("aprobado", "concesionado") for l in logs)
            rec.can_apariencia = bool(tacho_ok and acabado_ok)

    def action_evaluar_tono(self):
        self.ensure_one()
        if not self.can_eval_tono:
            raise UserError(
                "La evaluación de Tono Tacho solo está disponible cuando exista un proceso que contenga 'TEÑIDO' "
                "con inicio y fin, y mientras no exista un Tacho aprobado o concesionado."
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

    def action_apariencia(self):
        self.ensure_one()
        if not self.can_apariencia:
            raise UserError(
                "Apariencia solo está disponible cuando existan evaluaciones finales de Tono Tacho y Tono Acabado "
                "(Aprobado o Concesionado)."
            )
        return {
            "type": "ir.actions.client",
            "name": "Evaluar Apariencia",
            "tag": "idtx_quality.defect_screen",
        }

    # ---------- Tablet Tono Screen ----------
    def _has_tenido_cerrado(self):
        self.ensure_one()
        procesos_tenido = self.proceso_ids.filtered(
            lambda p: "TEÑIDO" in ((p.fasCod or "").strip().upper())
        )
        return any(p.barFasDTI and p.barFasDTF for p in procesos_tenido)

    def _get_tono_tablet_state(self):
        self.ensure_one()

        if self.can_eval_tono:
            return {
                "can_evaluate": True,
                "mode": "tacho",
                "reason": "",
            }

        if self.can_eval_tono_acabado:
            return {
                "can_evaluate": True,
                "mode": "acabado",
                "reason": "",
            }

        if not self._has_tenido_cerrado():
            reason = (
                "La evaluación de tono está disponible cuando exista un proceso que contenga 'TEÑIDO' "
                "con inicio y fin."
            )
        elif self.end_tono:
            reason = "La evaluación de tono ya fue cerrada para esta partida."
        else:
            reason = "La partida no está disponible para evaluar tono en este momento."

        return {
            "can_evaluate": False,
            "mode": False,
            "reason": reason,
        }

    def _build_tono_partida_payload(self):
        self.ensure_one()
        state = self._get_tono_tablet_state()
        mode = state.get("mode")
        mode_label = "Tacho" if mode == "tacho" else "Acabado" if mode == "acabado" else "No disponible"
        return {
            "id": self.id,
            "label": f"{self.batch or '-'} | {self.pedido_id.customer or '-'}",
            "batch": self.batch or "",
            "customer": self.pedido_id.customer or "",
            "article": self.description or "",
            "color_name": self.colorname or "",
            "color_code": self.colorcode or "",
            "kilograms": self.kilograms or 0.0,
            "pedido": self.pedido_id.numordped or "",
            "hdr": self.route or "",
            "mode": mode,
            "mode_label": mode_label,
            "can_evaluate": bool(state.get("can_evaluate")),
            "reason": state.get("reason") or "",
        }

    @api.model
    def action_tablet_get_partidas_tono(self, query="", limit=20):
        query = (query or "").strip()
        domain = Domain([])
        if query:
            terms = [term.strip() for term in query.split(",") if term.strip()]
            if not terms:
                terms = [query]

            domains_per_term = []
            for term in terms:
                domains_per_term.append(
                    Domain.OR([
                        Domain("batch", "ilike", term),
                        Domain("pedido_id.customer", "ilike", term),
                        Domain("description", "ilike", term),
                        Domain("colorname", "ilike", term),
                        Domain("colorcode", "ilike", term),
                    ])
                )
            domain = Domain.AND(domains_per_term)

        safe_limit = min(max(int(limit or 20), 1), 100)
        lines = self.search(domain, order="batch desc, id desc", limit=safe_limit)
        return [line._build_tono_partida_payload() for line in lines]

    @api.model
    def action_tablet_get_tono_context(self, pedido_line_id):
        line = self.browse(int(pedido_line_id or 0))
        if not line.exists():
            raise UserError("La partida seleccionada no existe.")

        payload = line._build_tono_partida_payload()
        state = line._get_tono_tablet_state()
        mode = state.get("mode")

        ultimo_tacho = self.env["control.tono.eval.log"].search(
            [("pedido_line_id", "=", line.id), ("tono", "=", "tacho")],
            order="fecha_eval desc, id desc",
            limit=1,
        )

        payload.update({
            "receta": "",
            "receta_tono": (ultimo_tacho.receta_tono or "") if mode == "acabado" and ultimo_tacho else "",
            "show_motivos": bool(mode == "acabado"),
            "can_show_decision_buttons": bool(state.get("can_evaluate")),
        })
        return payload

    @api.model
    def action_tablet_submit_tono(
        self,
        pedido_line_id,
        decision,
        receta,
        receta_tono,
        motivo_tono=False,
        motivo_tacto=False,
        motivo_apariencia=False,
    ):
        line = self.browse(int(pedido_line_id or 0))
        if not line.exists():
            raise UserError("La partida seleccionada no existe.")

        decision = (decision or "").strip().lower()
        if decision not in ("aprobado", "concesionado", "rechazado"):
            raise UserError("Decisión inválida.")

        state = line._get_tono_tablet_state()
        if not state.get("can_evaluate"):
            raise UserError(state.get("reason") or "La partida no está disponible para evaluar tono.")

        mode = state.get("mode")

        receta = (receta or "").strip()
        receta_tono = (receta_tono or "").strip()
        if not receta or not receta_tono:
            raise UserError("Debes completar las recetas.")

        motivo_tono = bool(motivo_tono)
        motivo_tacto = bool(motivo_tacto)
        motivo_apariencia = bool(motivo_apariencia)
        has_motivos_selected = bool(motivo_tono or motivo_tacto or motivo_apariencia)

        if mode == "acabado":
            ultimo_tacho = self.env["control.tono.eval.log"].search(
                [("pedido_line_id", "=", line.id), ("tono", "=", "tacho")],
                order="fecha_eval desc, id desc",
                limit=1,
            )
            receta_tono = (ultimo_tacho.receta_tono or receta_tono).strip()

        if decision == "aprobado" and mode == "acabado" and has_motivos_selected:
            raise UserError("Si seleccionas motivos, debes usar Concesionado.")

        if decision == "concesionado" and mode == "acabado" and not has_motivos_selected:
            raise UserError("Debes seleccionar al menos un motivo para concesionar.")

        self.env["control.tono.eval.log"].sudo().create({
            "pedido_line_id": line.id,
            "tono": mode,
            "motivo_tono": motivo_tono,
            "motivo_tacto": motivo_tacto,
            "motivo_apariencia": motivo_apariencia,
            "resultado": decision,
            "receta_tono": receta_tono,
            "receta": receta,
            "user_id": self.env.user.id,
        })

        return {
            "ok": True,
            "mode": mode,
            "resultado": decision,
        }