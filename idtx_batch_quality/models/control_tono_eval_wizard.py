from odoo import models, fields, api
from odoo.exceptions import UserError


class ControlTonoEvalWizard(models.TransientModel):
    _name = "control.tono.eval.wizard"
    _description = "Evaluar Tono - Wizard"

    pedido_line_id = fields.Many2one("control.pedido.line", required=True, ondelete="cascade")

    # ---- Solo lectura (ordenado como pediste) ----
    cliente = fields.Char(string="Cliente", readonly=True)
    tela = fields.Char(string="Tela", readonly=True)
    pedido = fields.Char(string="Pedido", readonly=True)
    partida = fields.Char(string="Partida", readonly=True)
    hdr = fields.Char(string="HDR", readonly=True)

    color_code = fields.Char(string="Cod Color", readonly=True)
    color_name = fields.Char(string="Color", readonly=True)
    kilos = fields.Float(string="Kilos", readonly=True)

    # ---- Editables ----
    receta = fields.Char(string="Receta")
    receta_rutero = fields.Char(string="Receta Rutero", required=True)

    is_concesionado = fields.Boolean(compute="_compute_is_concesionado", store=False)

    @api.depends("receta", "receta_rutero")
    def _compute_is_concesionado(self):
        for w in self:
            r1 = (w.receta or "").strip()
            r2 = (w.receta_rutero or "").strip()
            w.is_concesionado = bool(r1 and r2 and (r1 != r2))

    # -------------------------
    # Helper SQL: Tela (BARCAD.BarSerDsc)
    # -------------------------
    def _get_tela_from_barcad(self, pedido, partida, barcod, barcodreo):
        if not (pedido and partida and barcod):
            return ""

        try:
            bcreo = int(str(barcodreo).strip() or "0")
        except Exception:
            bcreo = 0

        conn = None
        cursor = None
        try:
            conn = self.env["control.pedido"]._get_sql_connection()
            cursor = conn.cursor()

            query = """
                SELECT TOP 1 bc.BarSerDsc
                FROM BARCAD bc
                WHERE bc.BarItem2 = ?
                  AND bc.BarItem4 = ?
                  AND bc.BarCod = ?
                  AND ISNULL(bc.BarCodReo, 0) = ?
            """
            cursor.execute(query, pedido, partida, barcod, bcreo)
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
        pedido_num = pedido_rec.numordped if pedido_rec else ""
        cliente = pedido_rec.customer if pedido_rec else ""

        partida = line.batch or ""
        hdr = line.route or ""
        reproceso = line.barcodreo or ""

        tela = self._get_tela_from_barcad(
            pedido=pedido_num,
            partida=partida,
            barcod=hdr,
            barcodreo=reproceso,
        )

        res.update({
            "pedido_line_id": line.id,
            "cliente": cliente,
            "tela": tela,
            "pedido": pedido_num,
            "partida": partida,
            "hdr": hdr,
            "color_code": line.colorcode or "",
            "color_name": line.colorname or "",
            "kilos": line.kilograms or 0.0,

            # ✅ precargar si ya existía en la línea
            "receta": line.receta or "",
            "receta_rutero": line.receta_rutero or "",
        })
        return res

    # -------------------------
    # Acciones de botones
    # -------------------------
    def _validate_before_decision(self):
        self.ensure_one()
        if not (self.receta_rutero or "").strip():
            raise UserError("Debes ingresar 'Receta Rutero' para continuar.")
        line = self.pedido_line_id
        if not line._has_control_calidad_terminado():
            raise UserError("Solo puedes evaluar cuando CONTROL DE CALIDAD esté terminado (inicio y fin).")

    def action_aprobar(self):
        self.ensure_one()
        self._validate_before_decision()

        line = self.pedido_line_id
        r1 = (self.receta or "").strip()
        r2 = (self.receta_rutero or "").strip()

        resultado = "concesionado" if (r1 and r2 and r1 != r2) else "aprobado"

        line.write({
            "receta": self.receta,
            "receta_rutero": self.receta_rutero,
            "receta_resultado": resultado,
            "tono_evaluado": True,
        })
        return {"type": "ir.actions.act_window_close"}

    def action_rechazar(self):
        self.ensure_one()
        self._validate_before_decision()

        line = self.pedido_line_id
        line.write({
            "receta": self.receta,
            "receta_rutero": self.receta_rutero,
            "receta_resultado": "rechazado",
            # Si quieres que rechazar también cuente como evaluado, deja True.
            "tono_evaluado": True,
        })
        return {"type": "ir.actions.act_window_close"}