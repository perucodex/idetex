from markupsafe import Markup

from odoo import models, fields, api, _
from odoo.fields import Domain
from odoo.exceptions import UserError

class ControlPedidoLine(models.Model):
    _inherit = "control.pedido.line"

    report_name = fields.Char(string="Report Name", default=lambda self: _("New"), copy=False, index=True)
    laboratorio_record_ids = fields.One2many(
        "control.laboratorio.record",
        "pedido_line_id",
        string="Registros de Laboratorio",
    )
    has_laboratorio_records = fields.Boolean(compute="_compute_has_laboratorio_records", store=False)
    est_revirado_eval_id = fields.Many2one(
        "control.estabilidad.revirado.eval",
        string="Evaluacion Estabilidad/Revirado",
        compute="_compute_est_revirado_eval",
        search="_search_est_revirado_eval_id",
        store=False,
    )
    has_est_revirado_eval = fields.Boolean(compute="_compute_est_revirado_eval", store=False)
    est_ancho_avg_dimrev = fields.Float(related="est_revirado_eval_id.est_ancho_avg", readonly=True)
    est_largo_avg_dimrev = fields.Float(related="est_revirado_eval_id.est_largo_avg", readonly=True)
    revirado_m1_result_dimrev = fields.Float(related="est_revirado_eval_id.revirado_m1_result", readonly=True)
    revirado_m2_result_dimrev = fields.Float(related="est_revirado_eval_id.revirado_m2_result", readonly=True)
    revirado_promedio_dimrev = fields.Float(related="est_revirado_eval_id.revirado_promedio", readonly=True)
    wash_number_dimrev = fields.Integer(related="est_revirado_eval_id.wash_number", readonly=True)
    densidad_promedio_dimrev = fields.Float(related="est_revirado_eval_id.densidad_promedio", readonly=True)
    ancho_promedio_dimrev = fields.Float(related="est_revirado_eval_id.ancho_promedio", readonly=True)
    densidad_1_dimrev = fields.Float(compute="_compute_dimrev_samples", store=False)
    densidad_2_dimrev = fields.Float(compute="_compute_dimrev_samples", store=False)
    densidad_3_dimrev = fields.Float(compute="_compute_dimrev_samples", store=False)
    ancho_1_dimrev = fields.Float(compute="_compute_dimrev_samples", store=False)
    ancho_2_dimrev = fields.Float(compute="_compute_dimrev_samples", store=False)
    ancho_3_dimrev = fields.Float(compute="_compute_dimrev_samples", store=False)
    tono_eval_log_ids = fields.One2many(
        "control.tono.eval.log",
        "pedido_line_id",
        string="Evaluaciones",
    )
    can_eval_tono = fields.Boolean(compute="_compute_can_eval_tono", store=False)
    can_eval_tono_secado = fields.Boolean(compute="_compute_can_eval_tono_secado", store=False)
    can_eval_tono_acabado = fields.Boolean(compute="_compute_can_eval_tono_acabado", store=False)
    end_tono = fields.Boolean(compute="_compute_end_tono", store=False)
    has_tono_eval_logs = fields.Boolean(compute="_compute_has_tono_eval_logs", store=False)
    apariencia_line_ids = fields.One2many(
        "control.apariencia.line",
        "pedido_line_id",
        string="Apariencia",
    )
    apariencia_eval_ids = fields.One2many(
        "control.apariencia.eval",
        "pedido_line_id",
        string="Evaluaciones de Apariencia",
    )
    has_apariencia_lines = fields.Boolean(compute="_compute_has_apariencia_lines", store=False)
    can_apariencia = fields.Boolean(compute="_compute_can_apariencia", store=False)
    user_id = fields.Many2one(
        comodel_name='res.users',
        string="Qualityperson",
        compute='_compute_user_id',
        store=True, readonly=False, precompute=True, index=True,
        tracking=2,
        domain=lambda self: "[('all_group_ids', 'in', {}), ('share', '=', False), ('company_ids', '=', company_id)]".format(
            self.env.ref("quality.group_quality_manager").ids
        ))
    company_id = fields.Many2one(
        comodel_name='res.company',
        required=True, index=True,
        default=lambda self: self.env.company)
    
    @api.depends('pedido_id.customer')
    def _compute_user_id(self):
        for rec in self:
            partner_id = self.env['res.partner'].search([('name','ilike', rec.pedido_id.customer)], limit=1)
            if partner_id and not (rec._origin.id and rec.user_id):
                rec.user_id = (
                    (self.env.user.has_group('quality.group_quality_manager') and self.env.user)
                )

    @api.model_create_multi
    def create(self, vals_list):
        seq_model = self.env["ir.sequence"]
        for vals in vals_list:
            if vals.get("report_name", _("New")) == _("New"):
                vals["report_name"] = seq_model.next_by_code("control.pedido.line.report_name") or _("New")
        return super().create(vals_list)

    def _compute_est_revirado_eval(self):
        eval_model = self.env["control.estabilidad.revirado.eval"]
        for rec in self:
            eval_rec = eval_model.search([("pedido_line_id", "=", rec.id)], limit=1)
            rec.est_revirado_eval_id = eval_rec
            rec.has_est_revirado_eval = bool(eval_rec)

    @api.depends("laboratorio_record_ids")
    def _compute_has_laboratorio_records(self):
        for rec in self:
            rec.has_laboratorio_records = bool(rec.laboratorio_record_ids)

    def _search_est_revirado_eval_id(self, operator, value):
        eval_model = self.env["control.estabilidad.revirado.eval"]

        if operator in ("=", "!=") and not value:
            line_ids_with_eval = eval_model.search([]).mapped("pedido_line_id").ids
            if operator == "=":
                return [("id", "not in", line_ids_with_eval)]
            return [("id", "in", line_ids_with_eval)]

        if operator in ("=", "!=", "in", "not in"):
            evals = eval_model.search([("id", operator, value)])
            line_ids = evals.mapped("pedido_line_id").ids
            if operator in ("=", "in"):
                return [("id", "in", line_ids)]
            return [("id", "not in", line_ids)]

        return [("id", "=", 0)]

    @api.depends("est_revirado_eval_id", "est_revirado_eval_id.detail_line_ids.dato", "est_revirado_eval_id.detail_line_ids.measure_key")
    def _compute_dimrev_samples(self):
        for rec in self:
            eval_rec = rec.est_revirado_eval_id
            if not eval_rec:
                rec.densidad_1_dimrev = 0.0
                rec.densidad_2_dimrev = 0.0
                rec.densidad_3_dimrev = 0.0
                rec.ancho_1_dimrev = 0.0
                rec.ancho_2_dimrev = 0.0
                rec.ancho_3_dimrev = 0.0
                continue

            rec.densidad_1_dimrev = eval_rec._get_measure_value("den_1")
            rec.densidad_2_dimrev = eval_rec._get_measure_value("den_2")
            rec.densidad_3_dimrev = eval_rec._get_measure_value("den_3")
            rec.ancho_1_dimrev = eval_rec._get_measure_value("anc_1")
            rec.ancho_2_dimrev = eval_rec._get_measure_value("anc_2")
            rec.ancho_3_dimrev = eval_rec._get_measure_value("anc_3")

    @api.depends("tono_eval_log_ids")
    def _compute_has_tono_eval_logs(self):
        for rec in self:
            rec.has_tono_eval_logs = bool(rec.tono_eval_log_ids)

    @api.depends("apariencia_line_ids", "apariencia_eval_ids.line_ids")
    def _compute_has_apariencia_lines(self):
        for rec in self:
            rec.has_apariencia_lines = bool(rec.apariencia_line_ids or rec.apariencia_eval_ids)

    @api.depends(
        "tono_eval_log_ids.tono",
        "tono_eval_log_ids.resultado",
    )
    def _compute_can_eval_tono(self):
        for rec in self:
            logs_tacho = rec.tono_eval_log_ids.filtered(lambda l: l.tono == "tacho")
            logs_acabado = rec.tono_eval_log_ids.filtered(lambda l: l.tono == "acabado")
            tiene_tacho_ok = any(l.resultado in ("aprobado", "concesionado") for l in logs_tacho)
            tiene_acabado_final = any(l.resultado in ("aprobado", "concesionado") for l in logs_acabado)
            rec.can_eval_tono = (not tiene_tacho_ok) and (not tiene_acabado_final)

    @api.depends("tono_eval_log_ids.tono", "tono_eval_log_ids.resultado")
    def _compute_can_eval_tono_secado(self):
        for rec in self:
            logs_tacho = rec.tono_eval_log_ids.filtered(lambda l: l.tono == "tacho")
            logs_secado = rec.tono_eval_log_ids.filtered(lambda l: l.tono == "secado")
            logs_acabado = rec.tono_eval_log_ids.filtered(lambda l: l.tono == "acabado")

            tiene_tacho_ok = any(l.resultado in ("aprobado", "concesionado") for l in logs_tacho)
            tiene_secado_final = any(l.resultado in ("aprobado", "concesionado") for l in logs_secado)
            tiene_acabado_final = any(l.resultado in ("aprobado", "concesionado") for l in logs_acabado)
            rec.can_eval_tono_secado = tiene_tacho_ok and (not tiene_secado_final) and (not tiene_acabado_final)

    @api.depends("tono_eval_log_ids.tono", "tono_eval_log_ids.resultado")
    def _compute_can_eval_tono_acabado(self):
        for rec in self:
            logs_tacho = rec.tono_eval_log_ids.filtered(lambda l: l.tono == "tacho")
            logs_acabado = rec.tono_eval_log_ids.filtered(lambda l: l.tono == "acabado")

            tiene_tacho_ok = any(l.resultado in ("aprobado", "concesionado") for l in logs_tacho)
            tiene_acabado_final = any(l.resultado in ("aprobado", "concesionado") for l in logs_acabado)
            rec.can_eval_tono_acabado = tiene_tacho_ok and not tiene_acabado_final

    @api.depends("tono_eval_log_ids.tono", "tono_eval_log_ids.resultado")
    def _compute_end_tono(self):
        for rec in self:
            resultados = set(
                rec.tono_eval_log_ids.filtered(lambda l: l.tono == "acabado").mapped("resultado")
            )
            rec.end_tono = bool(resultados.intersection({"aprobado", "concesionado"}))

    @api.depends("tono_eval_log_ids.tono", "tono_eval_log_ids.resultado")
    def _compute_can_apariencia(self):
        for rec in self:
            logs = rec.tono_eval_log_ids
            tacho_ok = any(l.tono == "tacho" and l.resultado in ("aprobado", "concesionado") for l in logs)
            acabado_ok = any(l.tono == "acabado" and l.resultado in ("aprobado", "concesionado") for l in logs)
            rec.can_apariencia = bool(tacho_ok and acabado_ok)

    def action_evaluar_tono(self):
        self.ensure_one()
        if not self.can_eval_tono:
            raise UserError(
                "La evaluación de Tono Tacho ya no está disponible porque la partida ya tiene un cierre final "
                "(Tacho o Acabado aprobado/concesionado)."
            )
        return {
            "type": "ir.actions.act_window",
            "name": "Evaluar Tono Tacho",
            "res_model": "control.tono.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_pedido_line_id": self.id, "tone_mode": "tacho"},
        }

    def action_evaluar_tono_acabado(self):
        self.ensure_one()
        if not self.can_eval_tono_acabado:
            raise UserError(
                "La evaluación de Tono Acabado solo está disponible después de aprobar o concesionar Tono Tacho, "
                "y mientras no exista un cierre final de Acabado."
            )
        return {
            "type": "ir.actions.act_window",
            "name": "Evaluar Tono Acabado",
            "res_model": "control.tono.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_pedido_line_id": self.id, "tone_mode": "acabado"},
        }

    def action_evaluar_tono_secado(self):
        self.ensure_one()
        if not self.can_eval_tono_secado:
            raise UserError(
                "La evaluación de Tono Secado solo está disponible después de aprobar o concesionar Tono Tacho, "
                "y mientras no exista un cierre final de Secado o Acabado."
            )
        return {
            "type": "ir.actions.act_window",
            "name": "Evaluar Tono Secado",
            "res_model": "control.tono.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_pedido_line_id": self.id, "tone_mode": "secado"},
        }

    @staticmethod
    def _state_to_summary_status(state_value):
        return "Pasa" if state_value == "pass" else "Falla"

    def _get_dimrev_highest_wash_eval(self):
        self.ensure_one()
        return self.env["control.estabilidad.revirado.eval"].search([
            ("pedido_line_id", "=", self.id),
        ], order="wash_number desc, fecha_eval desc, id desc", limit=1)

    def _get_dimrev_first_wash_eval(self):
        self.ensure_one()
        wash1_evals = self.env["control.estabilidad.revirado.eval"].search([
            ("pedido_line_id", "=", self.id),
            ("wash_number", "=", 1),
        ], order="fecha_eval desc, id desc")
        # Prefer the latest 1st-wash evaluation with captured detail lines.
        detailed_eval = wash1_evals.filtered(lambda rec: bool(rec.detail_line_ids))[:1]
        return detailed_eval or wash1_evals[:1]

    def _get_solidez_latest_eval(self):
        self.ensure_one()
        return self.env["control.solidez.lavado.eval"].search([
            ("pedido_line_id", "=", self.id),
        ], order="fecha_eval desc, id desc", limit=1)

    def _laboratorio_summary_report_payload(self):
        self.ensure_one()

        dimrev_highest = self._get_dimrev_highest_wash_eval()
        dimrev_l1 = self._get_dimrev_first_wash_eval()
        solidez = self._get_solidez_latest_eval()

        analysis = self.product_id.analysis_id
        dim_thresholds = analysis.density_stability_twisting_id if analysis else False

        std_density = float(analysis.density or 0.0) if analysis else 0.0
        std_width = float(analysis.standard_width or 0.0) if analysis else 0.0

        width_from = float(dim_thresholds.width_shrinkage_from or 0.0) * 100 if dim_thresholds else 0.0
        width_to = float(dim_thresholds.width_shrinkage_to or 0.0) * 100 if dim_thresholds else 0.0
        length_from = float(dim_thresholds.length_shrinkage_from or 0.0) * 100 if dim_thresholds else 0.0
        length_to = float(dim_thresholds.length_shrinkage_to or 0.0) * 100 if dim_thresholds else 0.0
        twist_std = float(dim_thresholds.twist or 0.0) if dim_thresholds else 0.0
        tilt_std = float(dim_thresholds.tilt_wash or 0.0) if dim_thresholds else 0.0

        # Always resolve washing standards from Lab Dev, even when there is no solidez eval yet.
        labdev = self.lab_dev_line_id
        if not labdev and solidez:
            labdev = solidez.pedido_line_id.lab_dev_line_id
        if not labdev:
            labdev = self.env["lab.dev.line"].search([
                ("color_code", "=", self.colorcode),
            ], order="id desc", limit=1)
        washing = labdev.colorfastness_washing_id if labdev else False

        def _fmt_req_range(from_value, to_value, unit=""):
            if from_value and to_value:
                return f"{from_value:.2f} a {to_value:.2f}{unit}"
            if from_value:
                return f"&#8805; {from_value:.2f}{unit}"
            if to_value:
                return f"<= {to_value:.2f}{unit}"
            return "-"

        def _fmt_req_max(value, unit=""):
            return f"<= {value:.2f}{unit}" if value else "-"

        def _fmt_req_min(value, unit=""):
            return f"&#8805; {value:.2f}{unit}" if value else "-"

        def _fmt_tolerance_percent(value):
            if not value:
                return 0.0
            raw = float(value)
            return raw * 100.0 if abs(raw) <= 1.0 else raw

        density_tol_pct = _fmt_tolerance_percent(float(dim_thresholds.density or 0.0) if dim_thresholds else 0.0)
        width_tol_pct = _fmt_tolerance_percent(float(dim_thresholds.width or 0.0) if dim_thresholds else 0.0)

        dimrev_highest_state = dimrev_highest.state if dimrev_highest else "nodata"
        dimrev_l1_state = dimrev_l1.state if dimrev_l1 else "nodata"
        solidez_state = solidez.state if solidez else "nodata"

        test_rows = [
            {
                "test": "Densidad",
                "method": "ASTM D3776 - Opcion C",
                "notes": [],
                "requirement": _fmt_req_min(std_density, " g/m2"),
                "requirement_lines": [
                    f"g/m2 {std_density:.2f}" if std_density else "g/m2 -",
                    f"&#177; {density_tol_pct:.2f}%" if density_tol_pct else "&#177; -",
                ],
                "result": float(dimrev_l1.densidad_promedio or 0.0) if dimrev_l1 else 0.0,
                "status": "Pasa" if (dimrev_l1 and dimrev_l1.bool_densidad_promedio) else "Falla",
            },
            {
                "test": "Ancho",
                "method": "Medicion de ancho estandar",
                "notes": [],
                "requirement": _fmt_req_min(std_width, " m"),
                "requirement_lines": [
                    f"cm {std_width:.2f}" if std_width else "cm -",
                    f"&#177; {width_tol_pct:.2f}%" if width_tol_pct else "&#177; -",
                ],
                "result": float(dimrev_l1.ancho_promedio or 0.0) if dimrev_l1 else 0.0,
                "status": "Pasa" if (dimrev_l1 and dimrev_l1.bool_ancho_promedio) else "Falla",
            },
            {
                "test": "Estabilidad Dimensional %Ancho",
                "method": "AATCC TM 135-2018t   (1) (III) B",
                "notes": [
                    {"label": "Temperatura de lavado", "value": "41&#176;C &#177;3&#176;C"},
                    {"label": "Ciclo", "value": "Normal"},
                    {"label": "Secado", "value": "En linea"},
                    {"label": "Lastre", "value": "Tipo 1 - 100% Algodon"},
                ],
                "requirement": _fmt_req_range(width_from, width_to, "%"),
                "result": float(dimrev_highest.est_ancho_avg or 0.0) if dimrev_highest else 0.0,
                "status": "Pasa" if (dimrev_highest and dimrev_highest.bool_est_ancho_avg) else "Falla",
            },
            {
                "test": "Estabilidad Dimensional %Largo",
                "method": "AATCC TM 135-2018t",
                "notes": [],
                "requirement": _fmt_req_range(length_from, length_to, "%"),
                "result": float(dimrev_highest.est_largo_avg or 0.0) if dimrev_highest else 0.0,
                "status": "Pasa" if (dimrev_highest and dimrev_highest.bool_est_largo_avg) else "Falla",
            },
            {
                "test": "Revirado",
                "method": "AATCC TM179-2019, Metodo 1, opcion 1",
                "notes": [],
                "requirement": _fmt_req_max(twist_std, "%"),
                "result": float(dimrev_highest.revirado_promedio or 0.0) if dimrev_highest else 0.0,
                "status": "Pasa" if (dimrev_highest and dimrev_highest.bool_revirado_promedio) else "Falla",
            },
            {
                "test": "Inclinacion Antes de Lavar",
                "method": "Control interno de inclinacion",
                "notes": [],
                "requirement": _fmt_req_max(tilt_std, "°"),
                "requirement_lines": [
                    f"{tilt_std:.2f}&#176;" if tilt_std else "&#176; -",
                    "&#177; 1&#176;" if tilt_std else "&#177; -",
                ],
                "result": float(dimrev_l1.tilt_before or 0.0) if dimrev_l1 else 0.0,
                "status": "Pasa" if (dimrev_l1 and dimrev_l1.bool_tilt_before) else "Falla",
            },
            {
                "test": "Solidez al lavado Acelerado",
                "method": "AATCC TM 61-2013e - Test N 2A",
                "notes": [
                    {"label": "Temperatura", "value": "49&#176;C &#177;3&#176;C"},
                    {"label": "Tiempo", "value": "45 min"},
                    {"label": "N bolas", "value": "50"},
                    {"label": "Multifibra", "value": "N 10"},
                    {"label": "Detergente", "value": "WOB"},
                ],
                "requirement": _fmt_req_min(float(washing.color_change_degree or 0.0) if washing else 0.0),
                "requirement_pairs": [
                    {
                        "label": "Cambio de color",
                        "value": f"&#8805; {float(washing.color_change_degree or 0.0):.2f}" if washing else "-",
                    },
                    {
                        "label": "Migracion Acetato",
                        "value": f"&#8805; {float(washing.migration_acetate or 0.0):.2f}" if washing else "-",
                    },
                    {
                        "label": "Migracion Algodon",
                        "value": f"&#8805; {float(washing.migration_cotton or 0.0):.2f}" if washing else "-",
                    },
                    {
                        "label": "Migracion Nylon",
                        "value": f"&#8805; {float(washing.migration_nylon or 0.0):.2f}" if washing else "-",
                    },
                    {
                        "label": "Migracion Poliester",
                        "value": f"&#8805; {float(washing.migration_polyester or 0.0):.2f}" if washing else "-",
                    },
                    {
                        "label": "Migracion Acrilico",
                        "value": f"&#8805; {float(washing.migration_acrylic or 0.0):.2f}" if washing else "-",
                    },
                    {
                        "label": "Migracion Lana",
                        "value": f"&#8805; {float(washing.migration_wool or 0.0):.2f}" if washing else "-",
                    },
                ],
                "requirement_lines": [
                    f"Cambio de color: &#8805; {float(washing.color_change_degree or 0.0):.2f}" if washing else "Cambio de color: -",
                    f"Migracion Acetato: &#8805; {float(washing.migration_acetate or 0.0):.2f}" if washing else "Migracion Acetato: -",
                    f"Migracion Algodon: &#8805; {float(washing.migration_cotton or 0.0):.2f}" if washing else "Migracion Algodon: -",
                    f"Migracion Nylon: &#8805; {float(washing.migration_nylon or 0.0):.2f}" if washing else "Migracion Nylon: -",
                    f"Migracion Poliester: &#8805; {float(washing.migration_polyester or 0.0):.2f}" if washing else "Migracion Poliester: -",
                    f"Migracion Acrilico: &#8805; {float(washing.migration_acrylic or 0.0):.2f}" if washing else "Migracion Acrilico: -",
                    f"Migracion Lana: &#8805; {float(washing.migration_wool or 0.0):.2f}" if washing else "Migracion Lana: -",
                ],
                "result": float(solidez.cambio_color_grado or 0.0) if solidez else 0.0,
                "result_lines": [
                    f"{float(solidez.cambio_color_grado or 0.0):.2f}" if solidez else "-",
                    f"{float(solidez.mig_acetato or 0.0):.2f}" if solidez else "-",
                    f"{float(solidez.mig_algodon or 0.0):.2f}" if solidez else "-",
                    f"{float(solidez.mig_nylon or 0.0):.2f}" if solidez else "-",
                    f"{float(solidez.mig_poliester or 0.0):.2f}" if solidez else "-",
                    f"{float(solidez.mig_acrilico or 0.0):.2f}" if solidez else "-",
                    f"{float(solidez.mig_lana or 0.0):.2f}" if solidez else "-",
                ],
                "status": "Pasa" if (
                    solidez
                    and solidez.bool_cambio_color_grado
                    and solidez.bool_mig_acetato
                    and solidez.bool_mig_algodon
                    and solidez.bool_mig_nylon
                    and solidez.bool_mig_poliester
                    and solidez.bool_mig_acrilico
                    and solidez.bool_mig_lana
                ) else "Falla",
            },
            {
                "test": "Solidez al frote",
                "method": "AATCC TM8-2016e",
                "notes": [],
                "requirement": _fmt_req_min(float(washing.colorfastness_to_dry_rubbing or 0.0) if washing else 0.0),
                "requirement_pairs": [
                    {
                        "label": "Seco",
                        "value": f"&#8805; {float(washing.colorfastness_to_dry_rubbing or 0.0):.2f}" if washing else "-",
                    },
                    {
                        "label": "Humedo",
                        "value": f"&#8805; {float(washing.colorfastness_to_wet_rubbing or 0.0):.2f}" if washing else "-",
                    },
                ],
                "result": float(solidez.frote_seco or 0.0) if solidez else 0.0,
                "result_lines": [
                    f"{float(solidez.frote_seco or 0.0):.2f}" if solidez else "-",
                    f"{float(solidez.frote_humedo or 0.0):.2f}" if solidez else "-",
                ],
                "status": "Pasa" if (solidez and solidez.bool_frote_seco and solidez.bool_frote_humedo) else "Falla",
            },
        ]

        # Show each evaluation independently in the status summary.
        summary_rows = [
            {
                "item": row.get("test") or "-",
                "status": row.get("status") or "Falla",
            }
            for row in test_rows
        ]

        any_fail = any(row["status"] == "Falla" for row in summary_rows)
        overall_status = "Falla" if any_fail else "Pasa"

        # Keep symbol entities readable in QWeb with t-out, without deprecated t-raw.
        for row in test_rows:
            row["requirement"] = Markup(row.get("requirement") or "-")
            row["requirement_lines"] = [Markup(line) for line in (row.get("requirement_lines") or [])]
            row["requirement_pairs"] = [
                {
                    "label": pair.get("label") or "-",
                    "value": Markup(pair.get("value") or "-"),
                }
                for pair in (row.get("requirement_pairs") or [])
            ]
            for note in row.get("notes") or []:
                note["value"] = Markup(note.get("value") or "-")

        return {
            "dimrev_highest": {
                "exists": bool(dimrev_highest),
                "name": dimrev_highest.name if dimrev_highest else "-",
                "fecha_eval": dimrev_highest.fecha_eval if dimrev_highest else False,
                "wash_number": int(dimrev_highest.wash_number or 0) if dimrev_highest else 0,
                "wash_label": dimrev_highest._wash_label_from_number(dimrev_highest.wash_number) if dimrev_highest else "-",
                "state": self._state_to_summary_status(dimrev_highest_state),
                "est_ancho_avg": float(dimrev_highest.est_ancho_avg or 0.0) if dimrev_highest else 0.0,
                "est_largo_avg": float(dimrev_highest.est_largo_avg or 0.0) if dimrev_highest else 0.0,
                "revirado_promedio": float(dimrev_highest.revirado_promedio or 0.0) if dimrev_highest else 0.0,
            },
            "dimrev_l1": {
                "exists": bool(dimrev_l1),
                "name": dimrev_l1.name if dimrev_l1 else "-",
                "fecha_eval": dimrev_l1.fecha_eval if dimrev_l1 else False,
                "state": self._state_to_summary_status(dimrev_l1_state),
                "densidad_promedio": float(dimrev_l1.densidad_promedio or 0.0) if dimrev_l1 else 0.0,
                "ancho_promedio": float(dimrev_l1.ancho_promedio or 0.0) if dimrev_l1 else 0.0,
                "tilt_before": float(dimrev_l1.tilt_before or 0.0) if dimrev_l1 else 0.0,
                "tilt_after": float(dimrev_l1.tilt_after or 0.0) if dimrev_l1 else 0.0,
            },
            "solidez": {
                "exists": bool(solidez),
                "name": solidez.name if solidez else "-",
                "fecha_eval": solidez.fecha_eval if solidez else False,
                "state": self._state_to_summary_status(solidez_state),
                "cambio_color_grado": float(solidez.cambio_color_grado or 0.0) if solidez else 0.0,
                "frote_seco": float(solidez.frote_seco or 0.0) if solidez else 0.0,
                "frote_humedo": float(solidez.frote_humedo or 0.0) if solidez else 0.0,
            },
            "test_rows": test_rows,
            "summary_rows": summary_rows,
            "overall_status": overall_status,
        }

    def action_print_laboratorio_summary_report(self):
        self.ensure_one()
        template = self.env.ref("idtx_batch_quality.mail_template_laboratorio_summary_front", raise_if_not_found=False)
        recipient = self._get_mail_recipient_partner()
        base_url = self.env["ir.config_parameter"].sudo().get_param("web.base.url")

        ctx = {
            "default_model": "control.pedido.line",
            "default_res_ids": self.ids,
            "default_composition_mode": "comment",
            "default_email_layout_xmlid": "mail.mail_notification_layout_with_responsible_signature",
            "email_notification_allow_footer": True,
            "hide_mail_template_management_options": True,
            "force_email": True,
            # Always provide a fallback button URL.
            "action_button_url": f"{base_url}/web#id={self.id}&model=control.pedido.line&view_type=form",
        }
        if template:
            ctx["default_template_id"] = template.id
        if recipient:
            ctx["default_partner_ids"] = [recipient.id]
            if recipient.lang:
                ctx["lab_lang"] = recipient.lang
            if not recipient.user_ids:
                frontend_url = f"{base_url}/kiosk/control_pedido"
                ctx["frontend_button_url"] = frontend_url
                ctx["action_button_url"] = frontend_url

        return {
            "name": _("Enviar Resumen de Laboratorio"),
            "type": "ir.actions.act_window",
            "view_mode": "form",
            "res_model": "mail.compose.message",
            "views": [(False, "form")],
            "target": "new",
            "context": ctx,
        }

    def _get_mail_recipient_partner(self):
        self.ensure_one()
        customer_name = (self.pedido_id.customer or "").strip()
        if not customer_name:
            return False

        partner_model = self.env["res.partner"]
        exact = partner_model.search([
            ("name", "=", customer_name),
            ("email", "!=", False),
        ], limit=1)
        if exact:
            return exact

        return partner_model.search([
            ("name", "ilike", customer_name),
            ("email", "!=", False),
        ], order="id desc", limit=1)

    def action_apariencia(self):
        self.ensure_one()
        if not self.can_apariencia:
            raise UserError(
                "Apariencia solo está disponible cuando existan evaluaciones finales de Tono Tacho y Tono Acabado "
                "(Aprobado o Concesionado)."
            )
        return {
            "type": "ir.actions.client",
            "name": "Evaluar Apariencia",
            "tag": "idtx_quality.defect_screen",
        }

    # ---------- Tablet Tono Screen ----------
    def _has_tenido_cerrado(self):
        self.ensure_one()
        return True

    @staticmethod
    def _tono_barcodreo_rank(value):
        try:
            return float((value or "").strip())
        except (TypeError, ValueError, AttributeError):
            return 0.0

    def _get_tono_tablet_state(self):
        self.ensure_one()
        all_logs = self.tono_eval_log_ids
        current_rank = self._tono_barcodreo_rank(self.barcodreo)

        same_cycle_logs = all_logs.filtered(
            lambda l: self._tono_barcodreo_rank(l.barcodreo) == current_rank
        )

        tacho_final_logs = all_logs.filtered(
            lambda l: l.tono == "tacho" and l.resultado in ("aprobado", "concesionado")
        )
        max_tacho_rank = max(
            (self._tono_barcodreo_rank(log.barcodreo) for log in tacho_final_logs),
            default=0.0,
        )

        if same_cycle_logs:
            logs = same_cycle_logs
        elif current_rank > max_tacho_rank:
            # New reprocess cycle: allow starting again from Tacho.
            logs = self.env["control.tono.eval.log"]
        else:
            logs = all_logs

        tacho_ok = any(l.tono == "tacho" and l.resultado in ("aprobado", "concesionado") for l in logs)
        secado_final = any(l.tono == "secado" and l.resultado in ("aprobado", "concesionado") for l in logs)
        acabado_final = any(l.tono == "acabado" and l.resultado in ("aprobado", "concesionado") for l in logs)

        available_modes = []
        if self._has_tenido_cerrado() and not acabado_final:
            if not tacho_ok:
                available_modes = ["tacho"]
            else:
                # Tras Tacho se puede evaluar Secado y/o Acabado.
                if not secado_final:
                    available_modes.append("secado")
                available_modes.append("acabado")

        if available_modes:
            return {
                "can_evaluate": True,
                "mode": available_modes[0],
                "available_modes": available_modes,
                "reason": "",
            }

        if acabado_final:
            reason = "La evaluación de tono ya fue cerrada para esta partida."
        else:
            reason = "La partida no está disponible para evaluar tono en este momento."

        return {
            "can_evaluate": False,
            "mode": False,
            "available_modes": [],
            "reason": reason,
        }

    def _build_tono_partida_payload(self):
        self.ensure_one()
        state = self._get_tono_tablet_state()
        mode = state.get("mode")
        mode_labels = {"tacho": "Tacho", "secado": "Secado", "acabado": "Acabado"}
        available_modes = state.get("available_modes") or ([] if not mode else [mode])
        mode_label = " / ".join(mode_labels.get(m, m) for m in available_modes) if available_modes else "No disponible"
        return {
            "id": self.id,
            "label": f"{self.batch or '-'} | {self.pedido_id.customer or '-'}",
            "batch": self.batch or "",
            "customer": self.pedido_id.customer or "",
            "article": self.description or "",
            "color_name": self.colorname or "",
            "color_code": self.colorcode or "",
            "kilograms": self.kilograms or 0.0,
            "pedido": self.pedido_id.numordped or "",
            "hdr": self.route or "",
            "mode": mode,
            "mode_label": mode_label,
            "available_modes": available_modes,
            "can_evaluate": bool(state.get("can_evaluate")),
            "reason": state.get("reason") or "",
        }

    @staticmethod
    def _tono_mode_labels():
        return {
            "tacho": "Tacho",
            "secado": "Secado",
            "acabado": "Acabado",
        }

    def _get_tono_state_for_lines(self, lines):
        self.ensure_one()
        if not lines:
            return {
                "can_evaluate": False,
                "mode": False,
                "available_modes": [],
                "reason": "No hay partidas seleccionadas.",
            }

        common_modes = None
        first_reason = ""
        for line in lines:
            state = line._get_tono_tablet_state()
            if not state.get("can_evaluate"):
                first_reason = first_reason or state.get("reason") or "La partida no está disponible para evaluar tono."
                return {
                    "can_evaluate": False,
                    "mode": False,
                    "available_modes": [],
                    "reason": first_reason,
                }

            line_modes = state.get("available_modes") or ([] if not state.get("mode") else [state.get("mode")])
            if common_modes is None:
                common_modes = set(line_modes)
            else:
                common_modes &= set(line_modes)

        ordered_modes = [m for m in ("tacho", "secado", "acabado") if common_modes and m in common_modes]
        if not ordered_modes:
            return {
                "can_evaluate": False,
                "mode": False,
                "available_modes": [],
                "reason": "Las partidas seleccionadas no comparten un mismo modo de evaluación.",
            }

        return {
            "can_evaluate": True,
            "mode": ordered_modes[0],
            "available_modes": ordered_modes,
            "reason": "",
        }

    @api.model
    def action_tablet_get_partidas_tono(self, query="", limit=20):
        query = (query or "").strip()
        domain = Domain([])
        if query:
            terms = [term.strip() for term in query.split(",") if term.strip()]
            if not terms:
                terms = [query]

            domains_per_term = []
            for term in terms:
                domains_per_term.append(
                    Domain.OR([
                        Domain("batch", "ilike", term),
                        Domain("pedido_id.customer", "ilike", term),
                        Domain("description", "ilike", term),
                        Domain("colorname", "ilike", term),
                        Domain("colorcode", "ilike", term),
                    ])
                )
            domain = Domain.AND(domains_per_term)

        safe_limit = min(max(int(limit or 20), 1), 500)
        lines = self.search(domain, order="batch desc, id desc", limit=safe_limit)

        tacho_done_line_ids = set(
            self.env["control.tono.eval.log"].search([
                ("pedido_line_id", "in", lines.ids),
                ("tono", "=", "tacho"),
                ("resultado", "in", ["aprobado", "concesionado"]),
            ]).mapped("pedido_line_id").ids
        )

        grouped = {}
        for line in lines:
            batch_key = (line.batch or "").strip()
            is_rect = line.product_id.analysis_id.weave_type == "rect"
            has_tacho_done = line.id in tacho_done_line_ids
            group_key = f"line_{line.id}" if (is_rect or has_tacho_done) else (batch_key or f"line_{line.id}")
            if group_key not in grouped:
                grouped[group_key] = self.browse()
            grouped[group_key] |= line

        mode_labels = self._tono_mode_labels()
        payloads = []
        for group_key, group_lines in grouped.items():
            first = group_lines[:1]
            state = first._get_tono_state_for_lines(group_lines)
            available_modes = state.get("available_modes") or ([] if not state.get("mode") else [state.get("mode")])
            mode_label = " / ".join(mode_labels.get(m, m) for m in available_modes) if available_modes else "No disponible"

            if len(group_lines) > 1:
                product_names = [
                    (line.product_id.display_name or line.description or "")
                    for line in group_lines
                    if (line.product_id.display_name or line.description)
                ]
                unique_names = list(dict.fromkeys(product_names))
                article_value = "Agrupado: %s" % ", ".join(unique_names) if unique_names else "Agrupado"
            elif first.product_id.analysis_id.weave_type == "rect":
                article_value = first.product_id.display_name or first.description or ""
            else:
                article_value = first.description or ""

            payloads.append({
                "id": group_key,
                "line_ids": group_lines.ids,
                "line_count": len(group_lines),
                "label": f"{first.batch or '-'} | {first.pedido_id.customer or '-'}",
                "batch": first.batch or "",
                "customer": first.pedido_id.customer or "",
                "article": article_value,
                "color_name": first.colorname or "",
                "color_code": first.colorcode or "",
                "kilograms": float(sum(group_lines.mapped("kilograms")) or 0.0),
                "pedido": first.pedido_id.numordped or "",
                "hdr": first.route or "",
                "mode": state.get("mode"),
                "mode_label": mode_label,
                "available_modes": available_modes,
                "can_evaluate": bool(state.get("can_evaluate")),
                "reason": state.get("reason") or "",
            })

        return payloads

    @api.model
    def action_tablet_get_tono_context(self, pedido_line_ids):
        line_ids = []
        if isinstance(pedido_line_ids, int):
            line_ids = [pedido_line_ids]
        elif isinstance(pedido_line_ids, list):
            line_ids = [int(x) for x in pedido_line_ids if x]

        lines = self.browse(line_ids).exists()
        if not lines:
            raise UserError("No hay partidas seleccionadas.")

        state = lines[:1]._get_tono_state_for_lines(lines)
        mode = state.get("mode")
        available_modes = state.get("available_modes") or ([] if not mode else [mode])
        mode_labels = self._tono_mode_labels()

        ultimo_tacho = self.env["control.tono.eval.log"].search(
            [("pedido_line_id", "in", lines.ids), ("tono", "=", "tacho")],
            order="fecha_eval desc, id desc",
            limit=1,
        )

        batches = sorted({(b or "").strip() for b in lines.mapped("batch") if (b or "").strip()})
        customers = sorted({(c or "").strip() for c in lines.mapped("pedido_id.customer") if (c or "").strip()})
        articles = sorted({(a or "").strip() for a in lines.mapped("description") if (a or "").strip()})
        colors = sorted({(c or "").strip() for c in lines.mapped("colorname") if (c or "").strip()})

        return {
            "id": "|".join(str(x) for x in lines.ids),
            "line_ids": lines.ids,
            "line_count": len(lines),
            "batch": ", ".join(batches) if batches else "-",
            "customer": customers[0] if len(customers) == 1 else "Varios",
            "article": articles[0] if len(articles) == 1 else "Varios",
            "color_name": colors[0] if len(colors) == 1 else "Varios",
            "kilograms": float(sum(lines.mapped("kilograms")) or 0.0),
            "mode": mode,
            "mode_label": " / ".join(mode_labels.get(m, m) for m in available_modes) if available_modes else "No disponible",
            "available_modes": available_modes,
            "can_evaluate": bool(state.get("can_evaluate")),
            "reason": state.get("reason") or "",
            "receta": "",
            "receta_tono": (ultimo_tacho.receta_tono or "") if mode in ("secado", "acabado") and ultimo_tacho else "",
            "show_motivos": bool(mode == "acabado"),
            "can_show_decision_buttons": bool(state.get("can_evaluate")),
        }

    @api.model
    def action_tablet_submit_tono(
        self,
        pedido_line_id,
        decision,
        receta,
        receta_tono,
        motivo_tono=False,
        motivo_tacto=False,
        motivo_apariencia=False,
        mode=False,
    ):
        line_ids = []
        if isinstance(pedido_line_id, int):
            line_ids = [pedido_line_id]
        elif isinstance(pedido_line_id, list):
            line_ids = [int(x) for x in pedido_line_id if x]

        lines = self.browse(line_ids).exists()
        if not lines:
            raise UserError("No hay partidas seleccionadas.")

        expanded_lines = lines

        decision = (decision or "").strip().lower()
        if decision not in ("aprobado", "concesionado", "rechazado"):
            raise UserError("Decisión inválida.")

        state = expanded_lines[:1]._get_tono_state_for_lines(expanded_lines)
        if not state.get("can_evaluate"):
            raise UserError(state.get("reason") or "La partida no está disponible para evaluar tono.")

        selected_mode = (mode or state.get("mode") or "").strip().lower()
        available_modes = state.get("available_modes") or ([] if not state.get("mode") else [state.get("mode")])
        if selected_mode not in available_modes:
            raise UserError("El tipo de evaluación seleccionado no está disponible para esta partida.")

        receta = (receta or "").strip()
        receta_tono = (receta_tono or "").strip()
        if selected_mode != "secado" and (not receta or not receta_tono):
            raise UserError("Debes completar las recetas.")

        if selected_mode == "secado":
            receta = ""
            receta_tono = ""

        motivo_tono = bool(motivo_tono)
        motivo_tacto = bool(motivo_tacto)
        motivo_apariencia = bool(motivo_apariencia)
        has_motivos_selected = bool(motivo_tono or motivo_tacto or motivo_apariencia)

        if decision == "aprobado" and selected_mode == "acabado" and has_motivos_selected:
            raise UserError("Si seleccionas motivos, debes usar Concesionado.")

        if decision == "concesionado" and selected_mode == "acabado" and not has_motivos_selected:
            raise UserError("Debes seleccionar al menos un motivo para concesionar.")

        created_count = 0
        group = self.env["control.tono.eval.group"].sudo().create({
            "tono": selected_mode,
            "resultado": decision,
            "user_id": self.env.user.id,
        })

        for line in expanded_lines:
            line_state = line._get_tono_tablet_state()
            line_modes = line_state.get("available_modes") or ([] if not line_state.get("mode") else [line_state.get("mode")])
            if not line_state.get("can_evaluate") or selected_mode not in line_modes:
                raise UserError(
                    "La partida %s no permite evaluar en modo %s en este momento."
                    % (line.batch or line.display_name, selected_mode)
                )

            line_receta_tono = receta_tono
            if selected_mode in ("secado", "acabado"):
                ultimo_tacho = self.env["control.tono.eval.log"].search(
                    [
                        ("pedido_line_id", "=", line.id),
                        ("tono", "=", "tacho"),
                        ("barcodreo", "=", line.barcodreo or ""),
                    ],
                    order="fecha_eval desc, id desc",
                    limit=1,
                )
                if not ultimo_tacho:
                    ultimo_tacho = self.env["control.tono.eval.log"].search(
                        [("pedido_line_id", "=", line.id), ("tono", "=", "tacho")],
                        order="fecha_eval desc, id desc",
                        limit=1,
                    )
                line_receta_tono = (ultimo_tacho.receta_tono or receta_tono).strip() if selected_mode == "acabado" else ""

            self.env["control.tono.eval.log"].sudo().create({
                "pedido_line_id": line.id,
                "eval_group_id": group.id,
                "tono": selected_mode,
                "motivo_tono": motivo_tono,
                "motivo_tacto": motivo_tacto,
                "motivo_apariencia": motivo_apariencia,
                "resultado": decision,
                "receta_tono": line_receta_tono,
                "receta": receta,
                "barcodreo": line.barcodreo or "",
                "user_id": self.env.user.id,
            })

            self.env["control.tono.eval.group.line"].sudo().create({
                "group_id": group.id,
                "pedido_line_id": line.id,
            })
            created_count += 1

        return {
            "ok": True,
            "mode": selected_mode,
            "resultado": decision,
            "created_count": created_count,
            "group_id": group.id,
            "group_name": group.name,
        }