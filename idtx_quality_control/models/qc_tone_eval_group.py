from odoo import api, fields, models


class ControlTonoEvalGroup(models.Model):
    _name = "qc.tone.eval.group"
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = "Evaluacion Grupal de Tono"
    _order = "fecha_eval desc, id desc"

    name = fields.Char(string="Referencia", required=True, copy=False, default="New", index=True)
    fecha_eval = fields.Datetime(string="Fecha", required=True, default=fields.Datetime.now, index=True)
    user_id = fields.Many2one("res.users", string="Usuario", required=True, default=lambda self: self.env.user)
    tono = fields.Selection(
        [("tacho", "Tacho"), ("secado", "Secado"), ("acabado", "Acabado")],
        string="Tipo de Tono",
        required=True,
        index=True,
    )
    resultado = fields.Selection(
        [("aprobado", "APROBADO"), ("concesionado", "CONCESIONADO"), ("rechazado", "RECHAZADO")],
        string="Resultado",
        required=True,
        index=True,
    )
    line_ids = fields.One2many("qc.tone.eval.group.line", "group_id", string="Partidas")
    total_count = fields.Integer(string="Partidas Evaluadas", compute="_compute_total_count", store=True)

    @api.depends("line_ids")
    def _compute_total_count(self):
        for rec in self:
            rec.total_count = len(rec.line_ids)

    @api.model_create_multi
    def create(self, vals_list):
        seq = self.env["ir.sequence"]
        for vals in vals_list:
            if vals.get("name", "New") == "New":
                vals["name"] = seq.next_by_code("qc.tone.eval.group") or "New"
        return super().create(vals_list)

    def unlink(self):
        # Remove linked logs with bypass context so grouped deletion works end-to-end.
        self.env["qc.tone.eval.log"].with_context(allow_group_eval_log_unlink=True).search(
            [("eval_group_id", "in", self.ids)]
        ).unlink()
        return super(ControlTonoEvalGroup, self.with_context(skip_group_line_chatter=True)).unlink()


class ControlTonoEvalGroupLine(models.Model):
    _name = "qc.tone.eval.group.line"
    _description = "Partidas en Evaluacion Grupal de Tono"
    _order = "id asc"

    group_id = fields.Many2one(
        "qc.tone.eval.group",
        string="Grupo",
        required=True,
        ondelete="cascade",
        index=True,
    )
    batch_id = fields.Many2one("mrp.workorder.batch", string="Partida", required=True, index=True)

    customer = fields.Char(string="Cliente", related="batch_id.qc_customer", store=False, readonly=True)
    article = fields.Char(string="Articulo", related="batch_id.qc_article", store=False, readonly=True)
    kilograms = fields.Float(string="Kilos", related="batch_id.kilograms", store=False, readonly=True)

    def unlink(self):
        if self.env.context.get("skip_group_line_chatter"):
            return super().unlink()

        grouped_lines = {}
        for line in self:
            group = line.group_id
            if not group:
                continue
            grouped_lines.setdefault(group.id, {"group": group, "labels": []})
            label = line.batch_id.name or line.batch_id.display_name or str(line.batch_id.id)
            grouped_lines[group.id]["labels"].append(label)

        result = super().unlink()

        for payload in grouped_lines.values():
            group = payload["group"].exists()
            if not group:
                continue
            labels = ", ".join(payload["labels"])
            group.message_post(body=f"Se eliminaron partidas del grupo: {labels}")

        return result
