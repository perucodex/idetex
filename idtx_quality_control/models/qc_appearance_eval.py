from odoo import api, fields, models, _
from odoo.exceptions import UserError
import statistics


class ControlAparienciaEval(models.Model):
    _name = "qc.appearance.eval"
    _description = "Evaluacion de Apariencia"
    _order = "create_date desc, id desc"

    _SAMPLE_TYPE_SELECTION = [
        ("seco_ppe", "Seco PPE"),
        ("empastado_digital", "Empastado Digital"),
        ("seco_estampado_rama", "Seco Estampado Rama"),
        ("acabado", "Acabado"),
        ("sanforizado_compactado", "Sanforizado y Compactado"),
        ("estampado", "Estampado"),
    ]

    name = fields.Char(string="Evaluacion", default=lambda self: _('New'), required=True, copy=False)
    batch_id = fields.Many2one(
        "mrp.workorder.batch",
        string="Partida",
        required=True,
        ondelete="cascade",
        index=True,
    )
    apariencia_id = fields.Many2one(
        "qc.appearance",
        string="Apariencia",
        required=True,
        index=True,
    )
    sample_type = fields.Selection(
        _SAMPLE_TYPE_SELECTION,
        string="Tipo de Muestra",
        required=True,
        default="acabado",
        index=True,
    )
    line_ids = fields.One2many(
        "qc.appearance.line",
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
                vals["name"] = self.env["ir.sequence"].next_by_code("qc.appearance.eval") or _('New')
        return super().create(vals_list)

    def _to_tablet_payload(self):
        self.ensure_one()
        sample_type_label = dict(self._SAMPLE_TYPE_SELECTION).get(self.sample_type, self.sample_type or "")
        return {
            "id": self.id,
            "name": self.name,
            "label": f"{self.name} ({self.line_count} rollos)",
            "batch_id": self.batch_id.id,
            "apariencia_id": self.apariencia_id.id,
            "sample_type": self.sample_type,
            "sample_type_label": sample_type_label,
        }

    @classmethod
    def _normalize_sample_type(cls, sample_type):
        sample_type = sample_type or "acabado"
        sample_type = str(sample_type)
        valid_sample_types = {key for key, _label in cls._SAMPLE_TYPE_SELECTION}
        if sample_type not in valid_sample_types:
            raise UserError(_("Tipo de muestra invalido."))
        return sample_type

    def action_print_report(self):
        self.ensure_one()
        return self.env.ref("idtx_quality_control.action_report_apariencia_eval").report_action(self)

    @api.model
    def action_tablet_get_or_create_evaluacion(self, batch_id, apariencia_id, sample_type=False, evaluacion_id=False):
        batch_id = int(batch_id or 0)
        apariencia_id = int(apariencia_id or 0)
        # Backward compatibility with older callers that passed evaluacion_id as 3rd arg.
        if isinstance(sample_type, (int, float)) and not evaluacion_id:
            evaluacion_id = int(sample_type or 0)
            sample_type = False
        evaluacion_id = int(evaluacion_id or 0)
        sample_type = self._normalize_sample_type(sample_type)

        if not batch_id:
            raise UserError("Seleccione una partida valida.")
        if not apariencia_id:
            raise UserError("Seleccione un control de apariencia valido.")

        if evaluacion_id:
            evaluacion = self.browse(evaluacion_id)
            if (
                evaluacion.exists()
                and evaluacion.batch_id.id == batch_id
                and evaluacion.apariencia_id.id == apariencia_id
                and evaluacion.sample_type == sample_type
            ):
                return evaluacion._to_tablet_payload()

        evaluacion = self.create({
            "batch_id": batch_id,
            "apariencia_id": apariencia_id,
            "sample_type": sample_type,
        })
        return evaluacion._to_tablet_payload()