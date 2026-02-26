from odoo import api, fields, models
from odoo.exceptions import UserError


class ControlAparienciaWizard(models.TransientModel):
    _name = "control.apariencia.wizard"
    _description = "Wizard Apariencia por Rollo"

    pedido_line_id = fields.Many2one("control.pedido.line", required=True, ondelete="cascade")

    # Datos informativos (readonly)
    cliente = fields.Char(string="Cliente", readonly=True)
    articulo = fields.Char(string="Articulo", readonly=True)
    pedido = fields.Char(string="Pedido", readonly=True)
    partida = fields.Char(string="Partida", readonly=True)
    hdr = fields.Char(string="Ruta", readonly=True)
    color_code = fields.Char(string="Cod Color", readonly=True)
    color_name = fields.Char(string="Color", readonly=True)
    kilos = fields.Float(string="Kilos", readonly=True)

    # Input
    rollo_num = fields.Integer(string="N° Rollo", required=True)

    lineas_aceite = fields.Integer(string="Lineas de aceite", default=0)
    cont_polipropileno = fields.Integer(string="Cont. Polipropileno", default=0)
    anillado = fields.Integer(string="Anillado", default=0)
    barraduras = fields.Integer(string="Barraduras", default=0)
    caida_tela = fields.Integer(string="Caida de tela", default=0)
    huecos = fields.Integer(string="Huecos", default=0)
    falla_aguja = fields.Integer(string="Falla de aguja", default=0)
    manchas_colorante = fields.Integer(string="Manchas de colorante", default=0)
    puntos_oxido = fields.Integer(string="Puntos de oxido", default=0)
    manchas_blancas = fields.Integer(string="Manchas blancas", default=0)
    jaladuras = fields.Integer(string="Jaladuras", default=0)
    raspaduras = fields.Integer(string="Raspaduras", default=0)
    migracion = fields.Integer(string="Migracion", default=0)
    quebraduras = fields.Integer(string="Quebraduras", default=0)
    manchas_suciedad = fields.Integer(string="Manchas de suciedad", default=0)
    mancha_grasa = fields.Integer(string="Mancha de grasa", default=0)
    remalles = fields.Integer(string="Remalles", default=0)
    ancho_variado = fields.Integer(string="Ancho variado", default=0)

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
            "articulo": (line.description or ""),
            "pedido": pedido_rec.numordped if pedido_rec else "",
            "partida": line.batch or "",
            "hdr": line.route or "",
            "color_code": line.colorcode or "",
            "color_name": line.colorname or "",
            "kilos": line.kilograms or 0.0,
        })
        return res

    def action_guardar(self):
        self.ensure_one()
        line = self.pedido_line_id

        if not line.can_apariencia:
            raise UserError(
                "No puedes registrar Apariencia sin tener evaluaciones finales de Tono Tacho y Tono Acabado."
            )

        if self.rollo_num <= 0:
            raise UserError("El N° Rollo debe ser mayor a 0.")

        self.env["control.apariencia.line"].sudo().create({
            "pedido_line_id": line.id,
            "rollo_num": self.rollo_num,

            "lineas_aceite": self.lineas_aceite,
            "cont_polipropileno": self.cont_polipropileno,
            "anillado": self.anillado,
            "barraduras": self.barraduras,
            "caida_tela": self.caida_tela,
            "huecos": self.huecos,
            "falla_aguja": self.falla_aguja,
            "manchas_colorante": self.manchas_colorante,
            "puntos_oxido": self.puntos_oxido,
            "manchas_blancas": self.manchas_blancas,
            "jaladuras": self.jaladuras,
            "raspaduras": self.raspaduras,
            "migracion": self.migracion,
            "quebraduras": self.quebraduras,
            "manchas_suciedad": self.manchas_suciedad,
            "mancha_grasa": self.mancha_grasa,
            "remalles": self.remalles,
            "ancho_variado": self.ancho_variado,
        })

        return {"type": "ir.actions.act_window_close"}