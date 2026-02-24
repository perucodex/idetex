from odoo import api, fields, models
from odoo.exceptions import UserError


class ControlTonoWizard(models.TransientModel):
    _name = "control.tono.wizard"
    _description = "Wizard Evaluar Tono"

    pedido_line_id = fields.Many2one("control.pedido.line", required=True, ondelete="cascade")

    cliente = fields.Char(string="Cliente", readonly=True)
    tela = fields.Char(string="Tela", readonly=True)
    pedido = fields.Char(string="Pedido", readonly=True)
    partida = fields.Char(string="Partida", readonly=True)
    hdr = fields.Char(string="Ruta", readonly=True)
    color_code = fields.Char(string="Cod Color", readonly=True)
    color_name = fields.Char(string="Color", readonly=True)
    kilos = fields.Float(string="Kilos", readonly=True)
    receta = fields.Char(string="Receta")
    receta_tono = fields.Char(string="Receta Tono")
    motivo = fields.Selection(
        [
            ("tono", "Tono"),
            ("tacto", "Tacto"),
            ("apariencia", "Apariencia"),
        ],
        string="Motivo",
    )
    can_show_decision_buttons = fields.Boolean(
        string="Puede decidir",
        compute="_compute_can_show_decision_buttons",
        store=False,
    )
    is_concesionado = fields.Boolean(
        string="Es concesionado",
        compute="_compute_is_concesionado",
        store=False,
    )

    @api.depends("receta_tono", "receta", "motivo")
    def _compute_can_show_decision_buttons(self):
        for w in self:
            if self.env.context.get("tono_acabado", False):
                w.can_show_decision_buttons = bool(
                    (w.receta or "").strip()
                    and (w.receta_tono   or "").strip()
                    and w.motivo
                )
            else:
                w.can_show_decision_buttons = bool(
                    (w.receta or "").strip()
                    and (w.receta_tono   or "").strip()
                )

    @api.depends("receta_tono", "receta", "can_show_decision_buttons")
    def _compute_is_concesionado(self):
        for w in self:
            if not w.can_show_decision_buttons:
                w.is_concesionado = False
                continue
            r_tono = (w.receta_tono or "").strip()
            r_acab = (w.receta or "").strip()
            w.is_concesionado = (r_tono != r_acab)

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

        res.update({
            "pedido_line_id": line.id,
            "cliente": pedido_rec.customer if pedido_rec else "",
            "tela": line._description or "",
            "pedido": pedido_rec.numordped if pedido_rec else "",
            "partida": line.batch or "",
            "hdr": line.route or "",
            "color_code": line.colorcode or "",
            "color_name": line.colorname or "",
            "kilos": line.kilograms or 0.0,
            "receta": "",
            "motivo": False,
        })
        print(self.env.context.get("tono_acabado", False))
        return res

    def _validate_before_decision(self):
        self.ensure_one()

        line = self.pedido_line_id

        if line.receta_resultado not in ("aprobado", "concesionado"):
            raise UserError("Primero debes cerrar la fase 'Evaluar Tono Tacho'.")

        if not (self.receta_tono or "").strip():
            raise UserError("No existe 'Receta Tacho' de la fase anterior.")
        if not (self.receta or "").strip():
            raise UserError("Debes ingresar 'Receta Acabado'.")
        if not self.motivo:
            raise UserError("Debes seleccionar un 'Motivo'.")

        resultados_acabado = set(line.tono_acabado_log_ids.mapped("resultado"))
        if resultados_acabado.intersection({"aprobado", "concesionado"}):
            raise UserError("Esta partida ya tiene una evaluación final en 'Tono Acabado'.")

    def _create_log(self, line, resultado):

        self.env["control.tono.eval.log"].sudo().create({
            "pedido_line_id": line.id,
            "tono": "acabado" if self.env.context.get("tono_acabado", False) else "tacho",
            "motivo": self.motivo,
            "resultado": resultado,
            "receta_tono": (self.receta_tono or "").strip(),
            "receta": (self.receta or "").strip(),
            'user_id': self.env.user.id,
        })

    def action_aprobar(self):

        r_tono = (self.receta_tono or "").strip()
        r_acab = (self.receta or "").strip()
        resultado = "concesionado" if (r_tono != r_acab) else "aprobado"

        line = self.pedido_line_id

        self._create_log(line, resultado)
        return

    def action_rechazar(self):

        line = self.pedido_line_id

        self._create_log(line, "rechazado")
        # return {"type": "ir.actions.act_window_close"}
        return