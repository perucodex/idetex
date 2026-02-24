from odoo import models, fields, api
from odoo.exceptions import UserError


class ControlPedidoLineTonoAcabado(models.Model):
    _inherit = "control.pedido.line"

    tono_acabado_evaluado = fields.Boolean(string="Tono Acabado evaluado", default=False)
    tono_acabado_receta = fields.Char(string="Receta Acabado")
    tono_acabado_motivo = fields.Selection(
        [
            ("tono", "Tono"),
            ("tacto", "Tacto"),
            ("apariencia", "Apariencia"),
        ],
        string="Motivo Acabado",
    )
    tono_acabado_resultado = fields.Selection(
        [
            ("aprobado", "APROBADO"),
            ("concesionado", "CONCESIONADO"),
            ("rechazado", "RECHAZADO"),
        ],
        string="Resultado Acabado",
    )

    tono_acabado_log_ids = fields.One2many(
        "control.tono.acabado.log",
        "pedido_line_id",
        string="Evaluaciones Acabado",
    )

    has_tono_acabado_logs = fields.Boolean(
        string="Tiene evaluaciones acabado",
        compute="_compute_has_tono_acabado_logs",
        store=False,
    )

    can_eval_tono_acabado = fields.Boolean(
        string="Puede evaluar tono acabado",
        compute="_compute_can_eval_tono_acabado",
        store=False,
    )

    @api.depends("tono_acabado_log_ids")
    def _compute_has_tono_acabado_logs(self):
        for rec in self:
            rec.has_tono_acabado_logs = bool(rec.tono_acabado_log_ids)

    @api.depends("receta_resultado", "tono_acabado_log_ids.resultado")
    def _compute_can_eval_tono_acabado(self):
        """
        Regla:
        - Solo se habilita si la fase Tacho ya cerró con APROBADO o CONCESIONADO.
        - Se puede seguir evaluando Acabado mientras NO tenga cierre final
          (APROBADO o CONCESIONADO) en acabado.
        - Si solo tiene RECHAZADO(s) en acabado, puede re-evaluar.
        """
        for rec in self:
            tacho_cerrado = rec.receta_resultado in ("aprobado", "concesionado")

            resultados_acabado = set(rec.tono_acabado_log_ids.mapped("resultado"))
            acabado_cerrado = bool(resultados_acabado.intersection({"aprobado", "concesionado"}))

            rec.can_eval_tono_acabado = bool(tacho_cerrado and not acabado_cerrado)

    def action_evaluar_tono_acabado(self):
        self.ensure_one()

        if self.receta_resultado not in ("aprobado", "concesionado"):
            raise UserError("Primero debes cerrar la fase 'Evaluar Tono Tacho' (Aprobado o Concesionado).")

        resultados_acabado = set(self.tono_acabado_log_ids.mapped("resultado"))
        if resultados_acabado.intersection({"aprobado", "concesionado"}):
            raise UserError("Esta partida ya tiene una evaluación final en 'Tono Acabado'.")

        return {
            "type": "ir.actions.act_window",
            "name": "Evaluar Tono Acabado",
            "res_model": "control.tono.acabado.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_pedido_line_id": self.id,
            },
        }


class ControlTonoAcabadoLog(models.Model):
    _name = "control.tono.acabado.log"
    _description = "Historial Evaluación Tono Acabado"
    _order = "fecha_eval asc, id asc"

    pedido_line_id = fields.Many2one(
        "control.pedido.line",
        string="Partida",
        required=True,
        ondelete="cascade",
        index=True,
    )

    fecha_eval = fields.Datetime(
        string="Fecha",
        default=fields.Datetime.now,
        required=True,
        index=True,
    )

    user_id = fields.Many2one(
        "res.users",
        string="Usuario",
        default=lambda self: self.env.user,
        required=True,
    )

    tono = fields.Char(string="Tono", default="Acabado", required=True)

    motivo = fields.Selection(
        [
            ("tono", "Tono"),
            ("tacto", "Tacto"),
            ("apariencia", "Apariencia"),
        ],
        string="Motivo",
        required=True,
    )

    resultado = fields.Selection(
        [
            ("aprobado", "APROBADO"),
            ("concesionado", "CONCESIONADO"),
            ("rechazado", "RECHAZADO"),
        ],
        string="Resultado",
        required=True,
        index=True,
    )

    receta_tacho = fields.Char(string="Receta Tacho", readonly=True)
    receta = fields.Char(string="Receta Acabado")
    pedido = fields.Char(string="Pedido", readonly=True)
    partida = fields.Char(string="Partida", readonly=True)
    hdr = fields.Char(string="Ruta", readonly=True)
    cliente = fields.Char(string="Cliente", readonly=True)
    tela = fields.Char(string="Tela", readonly=True)
    color_code = fields.Char(string="Cod Color", readonly=True)
    color_name = fields.Char(string="Color", readonly=True)
    kilos = fields.Float(string="Kilos", readonly=True)

    def _sync_line_after_log_change(self, lines):
        for line in lines.sudo():
            latest_log = line.tono_acabado_log_ids[-1:] if line.tono_acabado_log_ids else self.env["control.tono.acabado.log"]

            if latest_log:
                log = latest_log[0]
                line.write({
                    "tono_acabado_evaluado": True,
                    "tono_acabado_receta": log.receta or False,
                    "tono_acabado_motivo": log.motivo or False,
                    "tono_acabado_resultado": log.resultado or False,
                })
            else:
                line.write({
                    "tono_acabado_evaluado": False,
                    "tono_acabado_receta": False,
                    "tono_acabado_motivo": False,
                    "tono_acabado_resultado": False,
                })

    @api.model_create_multi
    def create(self, vals_list):
        logs = super().create(vals_list)
        logs._sync_line_after_log_change(logs.mapped("pedido_line_id"))
        return logs

    def unlink(self):
        lines = self.mapped("pedido_line_id")
        res = super().unlink()
        self._sync_line_after_log_change(lines)
        return res


class ControlTonoAcabadoWizard(models.TransientModel):
    _name = "control.tono.acabado.wizard"
    _description = "Wizard Evaluar Tono Acabado"

    pedido_line_id = fields.Many2one("control.pedido.line", required=True, ondelete="cascade")

    cliente = fields.Char(string="Cliente", readonly=True)
    tela = fields.Char(string="Tela", readonly=True)
    pedido = fields.Char(string="Pedido", readonly=True)
    partida = fields.Char(string="Partida", readonly=True)
    hdr = fields.Char(string="Ruta", readonly=True)
    color_code = fields.Char(string="Cod Color", readonly=True)
    color_name = fields.Char(string="Color", readonly=True)
    kilos = fields.Float(string="Kilos", readonly=True)

    receta_tacho = fields.Char(string="Receta Tacho", readonly=True)

    receta = fields.Char(string="Receta Acabado")
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

    @api.depends("receta_tacho", "receta", "motivo")
    def _compute_can_show_decision_buttons(self):
        for w in self:
            w.can_show_decision_buttons = bool(
                (w.receta_tacho or "").strip()
                and (w.receta or "").strip()
                and w.motivo
            )

    @api.depends("receta_tacho", "receta", "can_show_decision_buttons")
    def _compute_is_concesionado(self):
        for w in self:
            if not w.can_show_decision_buttons:
                w.is_concesionado = False
                continue
            r_tacho = (w.receta_tacho or "").strip()
            r_acab = (w.receta or "").strip()
            w.is_concesionado = (r_tacho != r_acab)

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)

        line_id = self.env.context.get("default_pedido_line_id")
        if not line_id:
            return res

        line = self.env["control.pedido.line"].browse(line_id)
        if not line.exists():
            return res

        if line.receta_resultado not in ("aprobado", "concesionado"):
            raise UserError("Primero debes cerrar la fase 'Evaluar Tono Tacho'.")

        tela_val = ""
        if line.tono_eval_log_ids:
            tela_val = (line.tono_eval_log_ids[-1].tela or "")
        pedido_rec = line.pedido_id

        res.update({
            "pedido_line_id": line.id,
            "cliente": pedido_rec.customer if pedido_rec else "",
            "tela": tela_val,
            "pedido": pedido_rec.numordped if pedido_rec else "",
            "partida": line.batch or "",
            "hdr": line.route or "",
            "color_code": line.colorcode or "",
            "color_name": line.colorname or "",
            "kilos": line.kilograms or 0.0,

            "receta_tacho": line.receta or "",
            "receta": "",
            "motivo": False,
        })
        return res

    def _validate_before_decision(self):
        self.ensure_one()

        line = self.pedido_line_id

        if line.receta_resultado not in ("aprobado", "concesionado"):
            raise UserError("Primero debes cerrar la fase 'Evaluar Tono Tacho'.")

        if not (self.receta_tacho or "").strip():
            raise UserError("No existe 'Receta Tacho' de la fase anterior.")
        if not (self.receta or "").strip():
            raise UserError("Debes ingresar 'Receta Acabado'.")
        if not self.motivo:
            raise UserError("Debes seleccionar un 'Motivo'.")

        resultados_acabado = set(line.tono_acabado_log_ids.mapped("resultado"))
        if resultados_acabado.intersection({"aprobado", "concesionado"}):
            raise UserError("Esta partida ya tiene una evaluación final en 'Tono Acabado'.")

    def _create_log(self, line, resultado):
        pedido_rec = line.pedido_id

        tela_val = ""
        if line.tono_eval_log_ids:
            tela_val = line.tono_eval_log_ids[-1].tela or ""

        self.env["control.tono.acabado.log"].sudo().create({
            "pedido_line_id": line.id,
            "tono": "Acabado",
            "motivo": self.motivo,
            "resultado": resultado,
            "receta_tacho": (self.receta_tacho or "").strip(),
            "receta": (self.receta or "").strip(),

            "pedido": pedido_rec.numordped if pedido_rec else "",
            "cliente": pedido_rec.customer if pedido_rec else "",
            "partida": line.batch or "",
            "hdr": line.route or "",
            "tela": tela_val,
            "color_code": line.colorcode or "",
            "color_name": line.colorname or "",
            "kilos": line.kilograms or 0.0,
        })

    def action_aprobar(self):
        self.ensure_one()
        self._validate_before_decision()

        r_tacho = (self.receta_tacho or "").strip()
        r_acab = (self.receta or "").strip()
        resultado = "concesionado" if (r_tacho != r_acab) else "aprobado"

        line = self.pedido_line_id
        line.write({
            "tono_acabado_evaluado": True,
            "tono_acabado_receta": r_acab,
            "tono_acabado_motivo": self.motivo,
            "tono_acabado_resultado": resultado,
        })

        self._create_log(line, resultado)
        return {"type": "ir.actions.act_window_close"}

    def action_rechazar(self):
        self.ensure_one()
        self._validate_before_decision()

        line = self.pedido_line_id
        line.write({
            "tono_acabado_evaluado": True,
            "tono_acabado_receta": (self.receta or "").strip(),
            "tono_acabado_motivo": self.motivo,
            "tono_acabado_resultado": "rechazado",
        })

        self._create_log(line, "rechazado")
        return {"type": "ir.actions.act_window_close"}