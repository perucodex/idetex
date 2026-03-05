from odoo import fields, models


class ControlTonoEvalLog(models.Model):
    _name = "control.tono.eval.log"
    _description = "Historial Evaluación Tono"
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
    tono = fields.Selection(
        [("tacho", "Tacho"), ("acabado", "Acabado")],
        string="Tono",
        required=True,
    )
    motivo_tono = fields.Boolean(string="Tono")
    motivo_tacto = fields.Boolean(string="Tacto")
    motivo_apariencia = fields.Boolean(string="Apariencia")
    resultado = fields.Selection(
        [("aprobado", "APROBADO"), ("concesionado", "CONCESIONADO"), ("rechazado", "RECHAZADO")],
        string="Resultado",
        required=True,
        index=True,
    )
    receta = fields.Char(string="Receta")
    receta_tono = fields.Char(string="Receta Tono", readonly=True)