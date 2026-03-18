from odoo import models, fields, api
from odoo.fields import Domain
from odoo.exceptions import UserError

class ControlPedidoLine(models.Model):
    _inherit = "control.pedido.line"

    laboratorio_record_ids = fields.One2many(
        "control.laboratorio.record",
        "pedido_line_id",
        string="Registros de Laboratorio",
    )
    has_laboratorio_records = fields.Boolean(compute="_compute_has_laboratorio_records", store=False)

    est_revirado_eval_id = fields.Many2one(
        "control.estabilidad.revirado.eval",
        string="Evaluacion Estabilidad/Revirado",
        compute="_compute_est_revirado_eval",
        search="_search_est_revirado_eval_id",
        store=False,
    )
    has_est_revirado_eval = fields.Boolean(compute="_compute_est_revirado_eval", store=False)

    est_ancho_avg_l1_dimrev = fields.Float(related="est_revirado_eval_id.est_ancho_avg_l1", readonly=True)
    est_ancho_avg_l3_dimrev = fields.Float(related="est_revirado_eval_id.est_ancho_avg_l3", readonly=True)
    est_ancho_avg_l5_dimrev = fields.Float(related="est_revirado_eval_id.est_ancho_avg_l5", readonly=True)
    est_largo_avg_l1_dimrev = fields.Float(related="est_revirado_eval_id.est_largo_avg_l1", readonly=True)
    est_largo_avg_l3_dimrev = fields.Float(related="est_revirado_eval_id.est_largo_avg_l3", readonly=True)
    est_largo_avg_l5_dimrev = fields.Float(related="est_revirado_eval_id.est_largo_avg_l5", readonly=True)

    revirado_m1_result_dimrev = fields.Float(related="est_revirado_eval_id.revirado_m1_result", readonly=True)
    revirado_m2_result_dimrev = fields.Float(related="est_revirado_eval_id.revirado_m2_result", readonly=True)
    revirado_promedio_dimrev = fields.Float(related="est_revirado_eval_id.revirado_promedio", readonly=True)
    revirado_n_lavado_dimrev = fields.Integer(related="est_revirado_eval_id.revirado_n_lavado", readonly=True)
    revirado_n_m1_result_dimrev = fields.Float(related="est_revirado_eval_id.revirado_n_m1_result", readonly=True)
    revirado_n_m2_result_dimrev = fields.Float(related="est_revirado_eval_id.revirado_n_m2_result", readonly=True)
    revirado_n_promedio_dimrev = fields.Float(related="est_revirado_eval_id.revirado_n_promedio", readonly=True)

    densidad_promedio_dimrev = fields.Float(related="est_revirado_eval_id.densidad_promedio", readonly=True)
    ancho_promedio_dimrev = fields.Float(related="est_revirado_eval_id.ancho_promedio", readonly=True)
    densidad_1_dimrev = fields.Float(compute="_compute_dimrev_samples", store=False)
    densidad_2_dimrev = fields.Float(compute="_compute_dimrev_samples", store=False)
    densidad_3_dimrev = fields.Float(compute="_compute_dimrev_samples", store=False)
    ancho_1_dimrev = fields.Float(compute="_compute_dimrev_samples", store=False)
    ancho_2_dimrev = fields.Float(compute="_compute_dimrev_samples", store=False)
    ancho_3_dimrev = fields.Float(compute="_compute_dimrev_samples", store=False)

    tono_eval_log_ids = fields.One2many(
        "control.tono.eval.log",
        "pedido_line_id",
        string="Evaluaciones",
    )

    can_eval_tono = fields.Boolean(compute="_compute_can_eval_tono", store=False)
    can_eval_tono_secado = fields.Boolean(compute="_compute_can_eval_tono_secado", store=False)
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

    def _compute_est_revirado_eval(self):
        eval_model = self.env["control.estabilidad.revirado.eval"]
        for rec in self:
            eval_rec = eval_model.search([("pedido_line_id", "=", rec.id)], limit=1)
            rec.est_revirado_eval_id = eval_rec
            rec.has_est_revirado_eval = bool(eval_rec)

    @api.depends("laboratorio_record_ids")
    def _compute_has_laboratorio_records(self):
        for rec in self:
            rec.has_laboratorio_records = bool(rec.laboratorio_record_ids)

    def _search_est_revirado_eval_id(self, operator, value):
        eval_model = self.env["control.estabilidad.revirado.eval"]

        if operator in ("=", "!=") and not value:
            line_ids_with_eval = eval_model.search([]).mapped("pedido_line_id").ids
            if operator == "=":
                return [("id", "not in", line_ids_with_eval)]
            return [("id", "in", line_ids_with_eval)]

        if operator in ("=", "!=", "in", "not in"):
            evals = eval_model.search([("id", operator, value)])
            line_ids = evals.mapped("pedido_line_id").ids
            if operator in ("=", "in"):
                return [("id", "in", line_ids)]
            return [("id", "not in", line_ids)]

        return [("id", "=", 0)]

    @api.depends("est_revirado_eval_id", "est_revirado_eval_id.detail_line_ids.dato", "est_revirado_eval_id.detail_line_ids.measure_key")
    def _compute_dimrev_samples(self):
        for rec in self:
            eval_rec = rec.est_revirado_eval_id
            if not eval_rec:
                rec.densidad_1_dimrev = 0.0
                rec.densidad_2_dimrev = 0.0
                rec.densidad_3_dimrev = 0.0
                rec.ancho_1_dimrev = 0.0
                rec.ancho_2_dimrev = 0.0
                rec.ancho_3_dimrev = 0.0
                continue

            rec.densidad_1_dimrev = eval_rec._get_measure_value("den_1")
            rec.densidad_2_dimrev = eval_rec._get_measure_value("den_2")
            rec.densidad_3_dimrev = eval_rec._get_measure_value("den_3")
            rec.ancho_1_dimrev = eval_rec._get_measure_value("anc_1")
            rec.ancho_2_dimrev = eval_rec._get_measure_value("anc_2")
            rec.ancho_3_dimrev = eval_rec._get_measure_value("anc_3")

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
    )
    def _compute_can_eval_tono(self):
        for rec in self:
            logs_tacho = rec.tono_eval_log_ids.filtered(lambda l: l.tono == "tacho")
            logs_acabado = rec.tono_eval_log_ids.filtered(lambda l: l.tono == "acabado")
            tiene_tacho_ok = any(l.resultado in ("aprobado", "concesionado") for l in logs_tacho)
            tiene_acabado_final = any(l.resultado in ("aprobado", "concesionado") for l in logs_acabado)
            rec.can_eval_tono = (not tiene_tacho_ok) and (not tiene_acabado_final)

    @api.depends("tono_eval_log_ids.tono", "tono_eval_log_ids.resultado")
    def _compute_can_eval_tono_secado(self):
        for rec in self:
            logs_tacho = rec.tono_eval_log_ids.filtered(lambda l: l.tono == "tacho")
            logs_secado = rec.tono_eval_log_ids.filtered(lambda l: l.tono == "secado")
            logs_acabado = rec.tono_eval_log_ids.filtered(lambda l: l.tono == "acabado")

            tiene_tacho_ok = any(l.resultado in ("aprobado", "concesionado") for l in logs_tacho)
            tiene_secado_final = any(l.resultado in ("aprobado", "concesionado") for l in logs_secado)
            tiene_acabado_final = any(l.resultado in ("aprobado", "concesionado") for l in logs_acabado)
            rec.can_eval_tono_secado = tiene_tacho_ok and (not tiene_secado_final) and (not tiene_acabado_final)

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
                "La evaluación de Tono Tacho ya no está disponible porque la partida ya tiene un cierre final "
                "(Tacho o Acabado aprobado/concesionado)."
            )
        return {
            "type": "ir.actions.act_window",
            "name": "Evaluar Tono Tacho",
            "res_model": "control.tono.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_pedido_line_id": self.id, "tone_mode": "tacho"},
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
            "context": {"default_pedido_line_id": self.id, "tone_mode": "acabado"},
        }

    def action_evaluar_tono_secado(self):
        self.ensure_one()
        if not self.can_eval_tono_secado:
            raise UserError(
                "La evaluación de Tono Secado solo está disponible después de aprobar o concesionar Tono Tacho, "
                "y mientras no exista un cierre final de Secado o Acabado."
            )
        return {
            "type": "ir.actions.act_window",
            "name": "Evaluar Tono Secado",
            "res_model": "control.tono.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_pedido_line_id": self.id, "tone_mode": "secado"},
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
        return True

    def _get_tono_tablet_state(self):
        self.ensure_one()
        logs = self.tono_eval_log_ids
        tacho_ok = any(l.tono == "tacho" and l.resultado in ("aprobado", "concesionado") for l in logs)
        secado_final = any(l.tono == "secado" and l.resultado in ("aprobado", "concesionado") for l in logs)
        acabado_final = any(l.tono == "acabado" and l.resultado in ("aprobado", "concesionado") for l in logs)

        available_modes = []
        if self._has_tenido_cerrado() and not acabado_final:
            if not tacho_ok:
                available_modes = ["tacho"]
            else:
                # Tras Tacho se puede evaluar Secado y/o Acabado.
                if not secado_final:
                    available_modes.append("secado")
                available_modes.append("acabado")

        if available_modes:
            return {
                "can_evaluate": True,
                "mode": available_modes[0],
                "available_modes": available_modes,
                "reason": "",
            }

        if acabado_final:
            reason = "La evaluación de tono ya fue cerrada para esta partida."
        else:
            reason = "La partida no está disponible para evaluar tono en este momento."

        return {
            "can_evaluate": False,
            "mode": False,
            "available_modes": [],
            "reason": reason,
        }

    def _build_tono_partida_payload(self):
        self.ensure_one()
        state = self._get_tono_tablet_state()
        mode = state.get("mode")
        mode_labels = {"tacho": "Tacho", "secado": "Secado", "acabado": "Acabado"}
        available_modes = state.get("available_modes") or ([] if not mode else [mode])
        mode_label = " / ".join(mode_labels.get(m, m) for m in available_modes) if available_modes else "No disponible"
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
            "available_modes": available_modes,
            "can_evaluate": bool(state.get("can_evaluate")),
            "reason": state.get("reason") or "",
        }

    @staticmethod
    def _tono_mode_labels():
        return {
            "tacho": "Tacho",
            "secado": "Secado",
            "acabado": "Acabado",
        }

    def _get_tono_state_for_lines(self, lines):
        self.ensure_one()
        if not lines:
            return {
                "can_evaluate": False,
                "mode": False,
                "available_modes": [],
                "reason": "No hay partidas seleccionadas.",
            }

        common_modes = None
        first_reason = ""
        for line in lines:
            state = line._get_tono_tablet_state()
            if not state.get("can_evaluate"):
                first_reason = first_reason or state.get("reason") or "La partida no está disponible para evaluar tono."
                return {
                    "can_evaluate": False,
                    "mode": False,
                    "available_modes": [],
                    "reason": first_reason,
                }

            line_modes = state.get("available_modes") or ([] if not state.get("mode") else [state.get("mode")])
            if common_modes is None:
                common_modes = set(line_modes)
            else:
                common_modes &= set(line_modes)

        ordered_modes = [m for m in ("tacho", "secado", "acabado") if common_modes and m in common_modes]
        if not ordered_modes:
            return {
                "can_evaluate": False,
                "mode": False,
                "available_modes": [],
                "reason": "Las partidas seleccionadas no comparten un mismo modo de evaluación.",
            }

        return {
            "can_evaluate": True,
            "mode": ordered_modes[0],
            "available_modes": ordered_modes,
            "reason": "",
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

        safe_limit = min(max(int(limit or 20), 1), 500)
        lines = self.search(domain, order="batch desc, id desc", limit=safe_limit)

        grouped = {}
        for line in lines:
            batch_key = (line.batch or "").strip()
            group_key = batch_key or f"line_{line.id}"
            if group_key not in grouped:
                grouped[group_key] = self.browse()
            grouped[group_key] |= line

        mode_labels = self._tono_mode_labels()
        payloads = []
        for group_key, group_lines in grouped.items():
            first = group_lines[:1]
            state = first._get_tono_state_for_lines(group_lines)
            available_modes = state.get("available_modes") or ([] if not state.get("mode") else [state.get("mode")])
            mode_label = " / ".join(mode_labels.get(m, m) for m in available_modes) if available_modes else "No disponible"
            payloads.append({
                "id": group_key,
                "line_ids": group_lines.ids,
                "line_count": len(group_lines),
                "label": f"{first.batch or '-'} | {first.pedido_id.customer or '-'}",
                "batch": first.batch or "",
                "customer": first.pedido_id.customer or "",
                "article": first.description or "",
                "color_name": first.colorname or "",
                "color_code": first.colorcode or "",
                "kilograms": float(sum(group_lines.mapped("kilograms")) or 0.0),
                "pedido": first.pedido_id.numordped or "",
                "hdr": first.route or "",
                "mode": state.get("mode"),
                "mode_label": mode_label,
                "available_modes": available_modes,
                "can_evaluate": bool(state.get("can_evaluate")),
                "reason": state.get("reason") or "",
            })

        return payloads

    @api.model
    def action_tablet_get_tono_context(self, pedido_line_ids):
        line_ids = []
        if isinstance(pedido_line_ids, int):
            line_ids = [pedido_line_ids]
        elif isinstance(pedido_line_ids, list):
            line_ids = [int(x) for x in pedido_line_ids if x]

        lines = self.browse(line_ids).exists()
        if not lines:
            raise UserError("No hay partidas seleccionadas.")

        state = lines[:1]._get_tono_state_for_lines(lines)
        mode = state.get("mode")
        available_modes = state.get("available_modes") or ([] if not mode else [mode])
        mode_labels = self._tono_mode_labels()

        ultimo_tacho = self.env["control.tono.eval.log"].search(
            [("pedido_line_id", "in", lines.ids), ("tono", "=", "tacho")],
            order="fecha_eval desc, id desc",
            limit=1,
        )

        batches = sorted({(b or "").strip() for b in lines.mapped("batch") if (b or "").strip()})
        customers = sorted({(c or "").strip() for c in lines.mapped("pedido_id.customer") if (c or "").strip()})
        articles = sorted({(a or "").strip() for a in lines.mapped("description") if (a or "").strip()})
        colors = sorted({(c or "").strip() for c in lines.mapped("colorname") if (c or "").strip()})

        return {
            "id": "|".join(str(x) for x in lines.ids),
            "line_ids": lines.ids,
            "line_count": len(lines),
            "batch": ", ".join(batches) if batches else "-",
            "customer": customers[0] if len(customers) == 1 else "Varios",
            "article": articles[0] if len(articles) == 1 else "Varios",
            "color_name": colors[0] if len(colors) == 1 else "Varios",
            "kilograms": float(sum(lines.mapped("kilograms")) or 0.0),
            "mode": mode,
            "mode_label": " / ".join(mode_labels.get(m, m) for m in available_modes) if available_modes else "No disponible",
            "available_modes": available_modes,
            "can_evaluate": bool(state.get("can_evaluate")),
            "reason": state.get("reason") or "",
            "receta": "",
            "receta_tono": (ultimo_tacho.receta_tono or "") if mode in ("secado", "acabado") and ultimo_tacho else "",
            "show_motivos": bool(mode == "acabado"),
            "can_show_decision_buttons": bool(state.get("can_evaluate")),
        }

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
        mode=False,
    ):
        line_ids = []
        if isinstance(pedido_line_id, int):
            line_ids = [pedido_line_id]
        elif isinstance(pedido_line_id, list):
            line_ids = [int(x) for x in pedido_line_id if x]

        lines = self.browse(line_ids).exists()
        if not lines:
            raise UserError("No hay partidas seleccionadas.")

        expanded_lines = lines

        decision = (decision or "").strip().lower()
        if decision not in ("aprobado", "concesionado", "rechazado"):
            raise UserError("Decisión inválida.")

        state = expanded_lines[:1]._get_tono_state_for_lines(expanded_lines)
        if not state.get("can_evaluate"):
            raise UserError(state.get("reason") or "La partida no está disponible para evaluar tono.")

        selected_mode = (mode or state.get("mode") or "").strip().lower()
        available_modes = state.get("available_modes") or ([] if not state.get("mode") else [state.get("mode")])
        if selected_mode not in available_modes:
            raise UserError("El tipo de evaluación seleccionado no está disponible para esta partida.")

        receta = (receta or "").strip()
        receta_tono = (receta_tono or "").strip()
        if selected_mode != "secado" and (not receta or not receta_tono):
            raise UserError("Debes completar las recetas.")

        if selected_mode == "secado":
            receta = ""
            receta_tono = ""

        motivo_tono = bool(motivo_tono)
        motivo_tacto = bool(motivo_tacto)
        motivo_apariencia = bool(motivo_apariencia)
        has_motivos_selected = bool(motivo_tono or motivo_tacto or motivo_apariencia)

        if decision == "aprobado" and selected_mode == "acabado" and has_motivos_selected:
            raise UserError("Si seleccionas motivos, debes usar Concesionado.")

        if decision == "concesionado" and selected_mode == "acabado" and not has_motivos_selected:
            raise UserError("Debes seleccionar al menos un motivo para concesionar.")

        created_count = 0
        group = self.env["control.tono.eval.group"].sudo().create({
            "tono": selected_mode,
            "resultado": decision,
            "user_id": self.env.user.id,
        })

        for line in expanded_lines:
            line_state = line._get_tono_tablet_state()
            line_modes = line_state.get("available_modes") or ([] if not line_state.get("mode") else [line_state.get("mode")])
            if not line_state.get("can_evaluate") or selected_mode not in line_modes:
                raise UserError(
                    "La partida %s no permite evaluar en modo %s en este momento."
                    % (line.batch or line.display_name, selected_mode)
                )

            line_receta_tono = receta_tono
            if selected_mode in ("secado", "acabado"):
                ultimo_tacho = self.env["control.tono.eval.log"].search(
                    [("pedido_line_id", "=", line.id), ("tono", "=", "tacho")],
                    order="fecha_eval desc, id desc",
                    limit=1,
                )
                line_receta_tono = (ultimo_tacho.receta_tono or receta_tono).strip() if selected_mode == "acabado" else ""

            self.env["control.tono.eval.log"].sudo().create({
                "pedido_line_id": line.id,
                "eval_group_id": group.id,
                "tono": selected_mode,
                "motivo_tono": motivo_tono,
                "motivo_tacto": motivo_tacto,
                "motivo_apariencia": motivo_apariencia,
                "resultado": decision,
                "receta_tono": line_receta_tono,
                "receta": receta,
                "user_id": self.env.user.id,
            })

            self.env["control.tono.eval.group.line"].sudo().create({
                "group_id": group.id,
                "pedido_line_id": line.id,
            })
            created_count += 1

        return {
            "ok": True,
            "mode": selected_mode,
            "resultado": decision,
            "created_count": created_count,
            "group_id": group.id,
            "group_name": group.name,
        }