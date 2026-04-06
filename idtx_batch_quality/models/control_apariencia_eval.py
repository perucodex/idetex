from odoo import api, fields, models, _
from odoo.exceptions import UserError
import statistics


class ControlAparienciaEval(models.Model):
    _name = "control.apariencia.eval"
    _description = "Evaluacion de Apariencia"
    _order = "create_date desc, id desc"

    name = fields.Char(string="Evaluacion", default=lambda self: _('New'), required=True, copy=False)
    pedido_line_id = fields.Many2one(
        "control.pedido.line",
        string="Partida",
        required=True,
        ondelete="cascade",
        index=True,
    )
    apariencia_id = fields.Many2one(
        "control.apariencia",
        string="Apariencia",
        required=True,
        index=True,
    )
    line_ids = fields.One2many(
        "control.apariencia.line",
        "evaluacion_id",
        string="Rollos Evaluados",
    )
    line_count = fields.Integer(string="Rollos", compute="_compute_line_count", store=False)
    quality_point = fields.Float(
        string="Quality Point",
        digits=(16, 2),
        compute="_compute_quality_point",
        store=True,
    )

    @api.depends("line_ids")
    def _compute_line_count(self):
        for rec in self:
            rec.line_count = len(rec.line_ids)

    @api.depends(
        "line_ids.width",
        "line_ids.meters",
        "line_ids.defecto_line_ids.tamano_defecto_ids.tamano",
        "line_ids.defecto_line_ids.tamano_defecto_ids.tamano_hueco",
        "line_ids.defecto_line_ids.defecto_id.is_hueco",
    )
    def _compute_quality_point(self):
        for rec in self:
            points = 0
            width = statistics.mean([roll.width for roll in rec.line_ids]) if rec.line_ids else 0
            meters = sum([roll.meters for roll in rec.line_ids]) if rec.line_ids else 0

            for roll in rec.line_ids:
                for tamano in roll.defecto_line_ids.tamano_defecto_ids:
                    if tamano.defecto_line_id.is_hueco:
                        points += int(tamano.tamano_hueco or 0)
                    else:
                        points += int(tamano.tamano or 0)

            rec.quality_point = ((points * 100) / (width * meters)) if width and meters else 0

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("name") or vals.get("name") == _('New'):
                vals["name"] = self.env["ir.sequence"].next_by_code("control.apariencia.eval") or _('New')
        return super().create(vals_list)

    def _to_tablet_payload(self):
        self.ensure_one()
        return {
            "id": self.id,
            "name": self.name,
            "label": f"{self.name} ({self.line_count} rollos)",
            "pedido_line_id": self.pedido_line_id.id,
            "apariencia_id": self.apariencia_id.id,
        }

    def action_print_report(self):
        self.ensure_one()
        return self.env.ref("idtx_batch_quality.action_report_apariencia_eval").report_action(self)

    @api.model
    def action_tablet_get_or_create_evaluacion(self, pedido_line_id, apariencia_id, evaluacion_id=False):
        pedido_line_id = int(pedido_line_id or 0)
        apariencia_id = int(apariencia_id or 0)
        evaluacion_id = int(evaluacion_id or 0)

        if not pedido_line_id:
            raise UserError("Seleccione una partida valida.")
        if not apariencia_id:
            raise UserError("Seleccione un control de apariencia valido.")

        if evaluacion_id:
            evaluacion = self.browse(evaluacion_id)
            if evaluacion.exists() and evaluacion.pedido_line_id.id == pedido_line_id and evaluacion.apariencia_id.id == apariencia_id:
                return evaluacion._to_tablet_payload()

        evaluacion = self.create({
            "pedido_line_id": pedido_line_id,
            "apariencia_id": apariencia_id,
        })
        return evaluacion._to_tablet_payload()