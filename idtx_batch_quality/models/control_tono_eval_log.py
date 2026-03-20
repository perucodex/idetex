from odoo import api, fields, models


class ControlTonoEvalLog(models.Model):
    _name = "control.tono.eval.log"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _description = "Historial Evaluación Tono"
    _order = "fecha_eval asc, id asc"

    pedido_line_id = fields.Many2one(
        "control.pedido.line",
        string="Partida",
        required=True,
        ondelete="cascade",
        index=True,
    )
    partida = fields.Char(
        string="Partida Ref",
        related="pedido_line_id.batch",
        readonly=True,
        store=False,
    )
    cliente = fields.Char(
        string="Cliente",
        related="pedido_line_id.pedido_id.customer",
        readonly=True,
        store=False,
    )
    color = fields.Char(
        string="Color",
        related="pedido_line_id.colorname",
        readonly=True,
        store=False,
    )
    eval_group_id = fields.Many2one(
        "control.tono.eval.group",
        string="Evaluacion Grupal",
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
        [("tacho", "Tacho"), ("secado", "Secado"), ("acabado", "Acabado")],
        string="Tipo de Tono",
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
        tracking=True,
    )
    receta = fields.Char(string="Receta")
    receta_tono = fields.Char(string="Receta Tono", readonly=True)
    user_has_group_quality_manager = fields.Boolean(compute="_compute_user_has_group_quality_manager")

    @api.depends_context("uid")
    def _compute_user_has_group_quality_manager(self):
        has_group = self.env.user.has_group("quality.group_quality_manager")
        for rec in self:
            rec.user_has_group_quality_manager = has_group

    def unlink(self):
        if self.env.context.get("allow_group_eval_log_unlink"):
            return super().unlink()

        # Keep track of grouped records to clean the group lines after deleting logs.
        grouped_pairs = [
            (log.eval_group_id.id, log.pedido_line_id.id)
            for log in self
            if log.eval_group_id and log.pedido_line_id
        ]
        grouped_ids = list({group_id for group_id, _line_id in grouped_pairs})

        result = super().unlink()

        if grouped_pairs:
            line_model = self.env["control.tono.eval.group.line"]
            log_model = self.env["control.tono.eval.log"]
            for group_id, line_id in set(grouped_pairs):
                remaining = log_model.search_count([
                    ("eval_group_id", "=", group_id),
                    ("pedido_line_id", "=", line_id),
                ])
                if not remaining:
                    line_model.search([
                        ("group_id", "=", group_id),
                        ("pedido_line_id", "=", line_id),
                    ]).unlink()

            group_model = self.env["control.tono.eval.group"]
            for group in group_model.browse(grouped_ids).exists():
                has_logs = log_model.search_count([("eval_group_id", "=", group.id)])
                if not has_logs and not group.line_ids:
                    group.unlink()

        return result
    
    def action_approve(self):
        self.motivo_tono = False
        self.motivo_tacto = False
        self.motivo_apariencia = False
        self.resultado = "aprobado"

    def action_conciliate(self):
        self.resultado = "concesionado"

    def action_reject(self):
        self.motivo_tono = False
        self.motivo_tacto = False
        self.motivo_apariencia = False
        self.resultado = "rechazado"