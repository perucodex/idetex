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

    receta = fields.Char(string="Receta")
    receta_tono = fields.Char(string="Receta Tono")
    motivo_tono = fields.Boolean(string="Tono")
    motivo_tacto = fields.Boolean(string="Tacto")
    motivo_apariencia = fields.Boolean(string="Apariencia")

    can_show_decision_buttons = fields.Boolean(compute="_compute_can_show_decision_buttons", store=False)
    is_concesionado = fields.Boolean(compute="_compute_is_concesionado", store=False)
    show_motivos = fields.Boolean(compute="_compute_show_motivos", store=False)

    @api.depends("receta_tono", "receta")
    def _compute_is_concesionado(self):
        for w in self:
            r_tono = (w.receta_tono or "").strip()
            r_actual = (w.receta or "").strip()
            w.is_concesionado = bool(r_tono and r_actual and r_tono != r_actual)

    @api.depends("receta_tono", "receta", "is_concesionado")
    def _compute_show_motivos(self):
        for w in self:
            es_acabado = bool(w.env.context.get("tono_acabado", False))
            w.show_motivos = es_acabado and w.is_concesionado

    @api.depends("receta_tono", "receta", "is_concesionado", "motivo_tono", "motivo_tacto", "motivo_apariencia")
    def _compute_can_show_decision_buttons(self):
        for w in self:
            r_tono = (w.receta_tono or "").strip()
            r_actual = (w.receta or "").strip()

            if not (r_tono and r_actual):
                w.can_show_decision_buttons = False
                continue

            es_acabado = bool(w.env.context.get("tono_acabado", False))
            if not es_acabado:
                w.can_show_decision_buttons = True
                continue

            if not w.is_concesionado:
                w.can_show_decision_buttons = True
            else:
                w.can_show_decision_buttons = bool(w.motivo_tono or w.motivo_tacto or w.motivo_apariencia)

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
        es_acabado = bool(self.env.context.get("tono_acabado", False))

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
            "receta": "",
            "receta_tono": (ultimo_tacho.receta_tono or "") if es_acabado and ultimo_tacho else "",
            "motivo_tono": False,
            "motivo_tacto": False,
            "motivo_apariencia": False,
        })
        return res

    def _motivos_texto(self):
        self.ensure_one()
        motivos = []
        if self.motivo_tono:
            motivos.append("Tono")
        if self.motivo_tacto:
            motivos.append("Tacto")
        if self.motivo_apariencia:
            motivos.append("Apariencia")
        return ", ".join(motivos)

    def _create_log(self, line, resultado):
        self.ensure_one()
        es_acabado = bool(self.env.context.get("tono_acabado", False))
        motivo_texto = self._motivos_texto() if es_acabado and self.is_concesionado else False

        self.env["control.tono.eval.log"].sudo().create({
            "pedido_line_id": line.id,
            "tono": "acabado" if es_acabado else "tacho",
            "motivo": motivo_texto,
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

        es_acabado = bool(self.env.context.get("tono_acabado", False))
        if es_acabado and r_tono != r_actual:
            if not (self.motivo_tono or self.motivo_tacto or self.motivo_apariencia):
                raise UserError("Debes seleccionar al menos un motivo.")

        resultado = "concesionado" if (r_tono != r_actual) else "aprobado"
        self._create_log(line, resultado)
        return {"type": "ir.actions.act_window_close"}

    def action_rechazar(self):
        self.ensure_one()
        line = self.pedido_line_id

        r_tono = (self.receta_tono or "").strip()
        r_actual = (self.receta or "").strip()
        if not r_tono or not r_actual:
            raise UserError("Debes completar las recetas.")

        es_acabado = bool(self.env.context.get("tono_acabado", False))
        if es_acabado and r_tono != r_actual:
            if not (self.motivo_tono or self.motivo_tacto or self.motivo_apariencia):
                raise UserError("Debes seleccionar al menos un motivo.")

        self._create_log(line, "rechazado")
        return {"type": "ir.actions.act_window_close"}