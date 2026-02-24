from odoo import models, fields, api
from odoo.exceptions import UserError


class ControlPedidoLine(models.Model):
    _inherit = "control.pedido.line"

    tono_evaluado = fields.Boolean(string="Tono evaluado", default=False)

    can_eval_tono = fields.Boolean(
        string="Puede evaluar tono",
        compute="_compute_can_eval_tono",
        store=False,
    )

    receta = fields.Char(string="Receta")
    receta_rutero = fields.Char(string="Receta Rutero")
    receta_resultado = fields.Selection(
        [
            ("aprobado", "APROBADO"),
            ("concesionado", "CONCESIONADO"),
            ("rechazado", "RECHAZADO"),
        ],
        string="Resultado Receta",
    )

    tono_eval_log_ids = fields.One2many(
        "control.tono.eval.log",
        "pedido_line_id",
        string="Evaluaciones",
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

    @api.depends("tono_eval_log_ids.resultado")
    def _compute_can_eval_tono(self):
        for rec in self:
            resultados = set(rec.tono_eval_log_ids.mapped("resultado"))
            rec.can_eval_tono = not bool(resultados.intersection({"aprobado", "concesionado"}))

    def action_evaluar_tono(self):
        self.ensure_one()
        resultados = set(self.tono_eval_log_ids.mapped("resultado"))
        if resultados.intersection({"aprobado", "concesionado"}):
            raise UserError("Esta partida ya tiene una evaluación final (APROBADO o CONCESIONADO).")

        return {
            "type": "ir.actions.act_window",
            "name": "Evaluar Tono Tacho",
            "res_model": "control.tono.eval.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_pedido_line_id": self.id},
        }


class ControlTonoEvalLog(models.Model):
    _name = "control.tono.eval.log"
    _description = "Historial Evaluación de Tono"
    _order = "fecha_eval asc, id asc"

    pedido_line_id = fields.Many2one("control.pedido.line", string="Partida", required=True, ondelete="cascade", index=True)
    fecha_eval = fields.Datetime(string="Fecha", default=fields.Datetime.now, required=True, index=True)
    user_id = fields.Many2one("res.users", string="Usuario", default=lambda self: self.env.user, required=True)
    tono = fields.Char(string="Tono", default="Tacho", required=True)

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

    receta = fields.Char(string="Receta")
    receta_rutero = fields.Char(string="Receta Rutero", required=True)

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
            latest_log = line.tono_eval_log_ids[-1:] if line.tono_eval_log_ids else self.env["control.tono.eval.log"]
            if latest_log:
                log = latest_log[0]
                line.write({
                    "tono_evaluado": True,
                    "receta": log.receta or False,
                    "receta_rutero": log.receta_rutero or False,
                    "receta_resultado": log.resultado or False,
                })
            else:
                line.write({
                    "tono_evaluado": False,
                    "receta": False,
                    "receta_rutero": False,
                    "receta_resultado": False,
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


class ControlTonoEvalWizard(models.TransientModel):
    _name = "control.tono.eval.wizard"
    _description = "Evaluar Tono - Wizard"

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
    receta_rutero = fields.Char(string="Receta Rutero")

    can_show_decision_buttons = fields.Boolean(compute="_compute_can_show_decision_buttons")
    is_concesionado = fields.Boolean(compute="_compute_is_concesionado")

    @api.depends("receta", "receta_rutero")
    def _compute_can_show_decision_buttons(self):
        for w in self:
            w.can_show_decision_buttons = bool((w.receta or "").strip() and (w.receta_rutero or "").strip())

    @api.depends("receta", "receta_rutero", "can_show_decision_buttons")
    def _compute_is_concesionado(self):
        for w in self:
            if not w.can_show_decision_buttons:
                w.is_concesionado = False
                continue
            w.is_concesionado = ((w.receta or "").strip() != (w.receta_rutero or "").strip())

    def _get_tela_from_barcad(self, pedido, partida, barcod, barcodreo):
        if not (pedido and partida and barcod):
            return ""
        try:
            bcreo = int(str(barcodreo).strip() or "0")
        except Exception:
            bcreo = 0

        conn = cursor = None
        try:
            conn = self.env["control.pedido"]._get_sql_connection()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT TOP 1 bc.BarSerDsc
                FROM BARCAD bc
                WHERE bc.BarItem2 = ?
                  AND bc.BarItem4 = ?
                  AND bc.BarCod = ?
                  AND ISNULL(bc.BarCodReo, 0) = ?
            """, pedido, partida, barcod, bcreo)
            row = cursor.fetchone()
            return (row[0] or "").strip() if row and row[0] else ""
        except Exception:
            return ""
        finally:
            try:
                if cursor:
                    cursor.close()
            except Exception:
                pass
            try:
                if conn:
                    conn.close()
            except Exception:
                pass

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
        tela = self._get_tela_from_barcad(
            pedido=pedido_rec.numordped if pedido_rec else "",
            partida=line.batch or "",
            barcod=line.route or "",
            barcodreo=line.barcodreo or "",
        )

        res.update({
            "pedido_line_id": line.id,
            "cliente": pedido_rec.customer if pedido_rec else "",
            "tela": tela,
            "pedido": pedido_rec.numordped if pedido_rec else "",
            "partida": line.batch or "",
            "hdr": line.route or "",
            "color_code": line.colorcode or "",
            "color_name": line.colorname or "",
            "kilos": line.kilograms or 0.0,
            "receta": "",
            "receta_rutero": "",
        })
        return res

    def _validate_before_decision(self):
        self.ensure_one()
        if not (self.receta or "").strip():
            raise UserError("Debes ingresar 'Receta' para continuar.")
        if not (self.receta_rutero or "").strip():
            raise UserError("Debes ingresar 'Receta Rutero' para continuar.")

        resultados = set(self.pedido_line_id.tono_eval_log_ids.mapped("resultado"))
        if resultados.intersection({"aprobado", "concesionado"}):
            raise UserError("Esta partida ya tiene una evaluación final (APROBADO o CONCESIONADO).")

    def _create_eval_log(self, line, resultado):
        pedido_rec = line.pedido_id
        self.env["control.tono.eval.log"].sudo().create({
            "pedido_line_id": line.id,
            "tono": "Tacho",
            "resultado": resultado,
            "receta": (self.receta or "").strip(),
            "receta_rutero": (self.receta_rutero or "").strip(),
            "pedido": pedido_rec.numordped if pedido_rec else "",
            "cliente": pedido_rec.customer if pedido_rec else "",
            "partida": line.batch or "",
            "hdr": line.route or "",
            "tela": self.tela or "",
            "color_code": line.colorcode or "",
            "color_name": line.colorname or "",
            "kilos": line.kilograms or 0.0,
        })

    def action_aprobar(self):
        self.ensure_one()
        self._validate_before_decision()
        line = self.pedido_line_id
        resultado = "concesionado" if (self.receta or "").strip() != (self.receta_rutero or "").strip() else "aprobado"

        line.write({
            "receta": (self.receta or "").strip(),
            "receta_rutero": (self.receta_rutero or "").strip(),
            "receta_resultado": resultado,
            "tono_evaluado": True,
        })
        self._create_eval_log(line, resultado)
        return {"type": "ir.actions.act_window_close"}

    def action_rechazar(self):
        self.ensure_one()
        self._validate_before_decision()
        line = self.pedido_line_id
        line.write({
            "receta": (self.receta or "").strip(),
            "receta_rutero": (self.receta_rutero or "").strip(),
            "receta_resultado": "rechazado",
            "tono_evaluado": True,
        })
        self._create_eval_log(line, "rechazado")
        return {"type": "ir.actions.act_window_close"}