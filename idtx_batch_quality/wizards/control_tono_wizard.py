from odoo import api, fields, models
from odoo.exceptions import UserError


class ControlTonoWizard(models.TransientModel):
    _name = "control.tono.wizard"
    _description = "Wizard Evaluar Tono"

    pedido_line_id = fields.Many2one("control.pedido.line", required=True, ondelete="cascade")

    cliente = fields.Char(string="Cliente", readonly=True)
    articulo = fields.Char(string="Articulo", readonly=True)
    pedido = fields.Char(string="Pedido", readonly=True)
    partida = fields.Char(string="Partida", readonly=True)
    hdr = fields.Char(string="Ruta", readonly=True)
    color_code = fields.Char(string="Cod Color", readonly=True)
    color_name = fields.Char(string="Color", readonly=True)
    kilos = fields.Float(string="Kilos", readonly=True)
    eval_mode = fields.Selection(
        [("tacho", "Tacho"), ("secado", "Secado"), ("acabado", "Acabado")],
        string="Tipo de Tono",
        required=True,
        default=lambda self: self._default_eval_mode(),
        readonly=True,
    )

    receta = fields.Char(string="Receta")
    receta_tono = fields.Char(string="Receta Tono")
    motivo_tono = fields.Boolean(string="Tono")
    motivo_tacto = fields.Boolean(string="Tacto")
    motivo_apariencia = fields.Boolean(string="Apariencia")

    can_show_decision_buttons = fields.Boolean(compute="_compute_can_show_decision_buttons", store=False)
    is_concesionado = fields.Boolean(compute="_compute_is_concesionado", store=False)
    show_motivos = fields.Boolean(compute="_compute_show_motivos", store=False)
    has_motivos_selected = fields.Boolean(compute="_compute_has_motivos_selected", store=False)

    @api.depends("motivo_tono", "motivo_tacto", "motivo_apariencia")
    def _compute_has_motivos_selected(self):
        for w in self:
            w.has_motivos_selected = bool(w.motivo_tono or w.motivo_tacto or w.motivo_apariencia)

    @api.depends("has_motivos_selected")
    def _compute_is_concesionado(self):
        for w in self:
            es_acabado = w.eval_mode == "acabado"
            w.is_concesionado = bool(es_acabado and w.has_motivos_selected)

    @api.depends("eval_mode")
    def _compute_show_motivos(self):
        for w in self:
            w.show_motivos = w.eval_mode == "acabado"

    @api.depends("eval_mode")
    def _compute_can_show_decision_buttons(self):
        for w in self:
            w.can_show_decision_buttons = True

    @api.model
    def _default_eval_mode(self):
        mode = (self.env.context.get("tone_mode") or "").strip().lower()
        if mode in ("tacho", "secado", "acabado"):
            return mode
        if self.env.context.get("tono_acabado"):
            return "acabado"
        return "tacho"

    def _ensure_mode_allowed(self):
        self.ensure_one()
        line = self.pedido_line_id
        logs = line.tono_eval_log_ids
        tacho_ok = any(l.tono == "tacho" and l.resultado in ("aprobado", "concesionado") for l in logs)
        secado_final = any(l.tono == "secado" and l.resultado in ("aprobado", "concesionado") for l in logs)
        acabado_final = any(l.tono == "acabado" and l.resultado in ("aprobado", "concesionado") for l in logs)

        if self.eval_mode == "tacho":
            if not line.can_eval_tono:
                raise UserError(
                    "La evaluación de Tono Tacho no está disponible para esta partida."
                )
            return

        if self.eval_mode == "secado":
            if not tacho_ok:
                raise UserError("Debes tener una evaluación Tacho aprobada o concesionada antes de Secado.")
            if secado_final:
                raise UserError("La evaluación de Tono Secado ya fue cerrada para esta partida.")
            if acabado_final:
                raise UserError("La partida ya fue cerrada en Acabado y no admite Secado.")
            return

        if self.eval_mode == "acabado":
            if not tacho_ok:
                raise UserError("Debes tener una evaluación Tacho aprobada o concesionada antes de Acabado.")
            if acabado_final:
                raise UserError("La evaluación de Tono Acabado ya fue cerrada para esta partida.")

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)

        line_id = self.env.context.get("default_pedido_line_id")
        if not line_id:
            return res

        line = self.env["control.pedido.line"].browse(line_id)
        if not line.exists():
            return res

        pedido_rec = line.pedido_id
        mode = res.get("eval_mode") or self._default_eval_mode()

        ultimo_tacho = self.env["control.tono.eval.log"].search(
            [("pedido_line_id", "=", line.id), ("tono", "=", "tacho")],
            order="fecha_eval desc, id desc",
            limit=1,
        )

        res.update({
            "pedido_line_id": line.id,
            "cliente": pedido_rec.customer if pedido_rec else "",
            "articulo": (line.description or ""),
            "pedido": pedido_rec.numordped if pedido_rec else "",
            "partida": line.batch or "",
            "hdr": line.route or "",
            "color_code": line.colorcode or "",
            "color_name": line.colorname or "",
            "kilos": line.kilograms or 0.0,
            "eval_mode": mode,
            "receta": "",
            "receta_tono": (ultimo_tacho.receta_tono or "") if mode in ("secado", "acabado") and ultimo_tacho else "",
            "motivo_tono": False,
            "motivo_tacto": False,
            "motivo_apariencia": False,
        })
        return res

    def _create_log(self, line, resultado):
        self.ensure_one()
        self._ensure_mode_allowed()

        self.env["control.tono.eval.log"].sudo().create({
            "pedido_line_id": line.id,
            "tono": self.eval_mode,
            "motivo_tono": self.motivo_tono,
            "motivo_tacto": self.motivo_tacto,
            "motivo_apariencia": self.motivo_apariencia,
            "resultado": resultado,
            "receta_tono": (self.receta_tono or "").strip(),
            "receta": (self.receta or "").strip(),
            "user_id": self.env.user.id,
        })

    def action_aprobar(self):
        self.ensure_one()
        line = self.pedido_line_id

        r_tono = (self.receta_tono or "").strip()
        r_actual = (self.receta or "").strip()
        if not r_tono or not r_actual:
            raise UserError("Debes completar las recetas.")

        es_acabado = self.eval_mode == "acabado"
        if es_acabado and self.has_motivos_selected:
            raise UserError("Si seleccionas motivos, debes usar Concesionar.")

        self._create_log(line, "aprobado")
        return {"type": "ir.actions.act_window_close"}

    def action_concesionar(self):
        self.ensure_one()
        line = self.pedido_line_id

        r_tono = (self.receta_tono or "").strip()
        r_actual = (self.receta or "").strip()
        if not r_tono or not r_actual:
            raise UserError("Debes completar las recetas.")

        es_acabado = self.eval_mode == "acabado"
        if es_acabado and not self.has_motivos_selected:
            raise UserError("Debes seleccionar al menos un motivo para concesionar.")

        self._create_log(line, "concesionado")
        return {"type": "ir.actions.act_window_close"}

    def action_rechazar(self):
        self.ensure_one()
        line = self.pedido_line_id

        r_tono = (self.receta_tono or "").strip()
        r_actual = (self.receta or "").strip()
        if not r_tono or not r_actual:
            raise UserError("Debes completar las recetas.")

        self._create_log(line, "rechazado")
        return {"type": "ir.actions.act_window_close"}