from odoo import _, api, fields, models
from odoo.exceptions import UserError


class ControlLaboratorioRecord(models.Model):
    _name = "control.laboratorio.record"
    _description = "Registro de Laboratorio por Partida"
    _order = "fecha_eval desc, id desc"

    pedido_line_id = fields.Many2one("control.pedido.line", string="Partida", required=True, ondelete="cascade", index=True)
    eval_number = fields.Char(string="Nro Evaluacion", required=True, readonly=True, copy=False, index=True)
    fecha_eval = fields.Datetime(string="Fecha", required=True, default=fields.Datetime.now, index=True)
    user_id = fields.Many2one("res.users", string="Usuario", required=True, default=lambda self: self.env.user)
    test_type = fields.Selection([
        ("dimrev", "Densidad + Estabilidad + Revirado"),
        ("solidez_lavado", "Solidez del Color al Lavado"),
        ("solidez_frote", "Solidez al Frote"),
        ("resistencia_estallido", "Resistencia al Estallido"),
    ], string="Tipo de Prueba", required=True, default="dimrev", index=True)
    result_state = fields.Selection([
        ("pasa", "Pasa"),
        ("falla", "Falla"),
    ], string="Estado", required=True, default="pasa", index=True)
    numero_lavado = fields.Char(string="Numero de Lavado", compute="_compute_numero_lavado", store=False)

    est_revirado_eval_id = fields.Many2one(
        "control.estabilidad.revirado.eval",
        string="Evaluacion Dimensional/Revirado",
        ondelete="cascade",
        index=True,
    )
    solidez_lavado_eval_id = fields.Many2one(
        "control.solidez.lavado.eval",
        string="Evaluacion Solidez del Color al Lavado",
        ondelete="cascade",
        index=True,
    )
    result_line_ids = fields.One2many(
        "control.laboratorio.record.result",
        "record_id",
        string="Resultados",
        copy=False,
    )

    _uniq_laboratorio_eval_number = models.Constraint(
        "UNIQUE(pedido_line_id, eval_number)",
        "El numero de evaluacion ya existe para esta partida.",
    )
    _uniq_dimrev_eval_link = models.Constraint(
        "UNIQUE(est_revirado_eval_id)",
        "La evaluacion de estabilidad/revirado ya tiene un registro de laboratorio.",
    )
    _uniq_solidez_lavado_eval_link = models.Constraint(
        "UNIQUE(solidez_lavado_eval_id)",
        "La evaluacion de solidez del color al lavado ya tiene un registro de laboratorio.",
    )

    @api.model_create_multi
    def create(self, vals_list):
        seq_model = self.env["ir.sequence"]
        for vals in vals_list:
            if vals.get("eval_number"):
                continue
            vals["eval_number"] = seq_model.next_by_code("control.laboratorio.record.eval_number") or "LABE00001"
        records = super().create(vals_list)
        records._sync_result_lines()
        return records

    def write(self, vals):
        res = super().write(vals)
        if any(k in vals for k in ("test_type", "est_revirado_eval_id", "solidez_lavado_eval_id", "result_state")):
            self._sync_result_lines()
        return res

    @staticmethod
    def _has_measure_prefix(eval_rec, prefix):
        return any((line.measure_key or "").startswith(prefix) for line in eval_rec.detail_line_ids)

    @staticmethod
    def _wash_avg_from_details(eval_rec, axis):
        m1 = sum(eval_rec._get_measure_value(f"st_{axis}_m1_d{d}") for d in (1, 2, 3)) / 3.0
        m2 = sum(eval_rec._get_measure_value(f"st_{axis}_m2_d{d}") for d in (1, 2, 3)) / 3.0
        return (m1 + m2) / 2.0

    @staticmethod
    def _revirado_promedio_from_values(m1_ac, m1_bd, m2_ac, m2_bd):
        den_m1 = m1_ac + m1_bd
        den_m2 = m2_ac + m2_bd
        r1 = (((m1_ac - m1_bd) / den_m1) * 200.0) if den_m1 else 0.0
        r2 = (((m2_ac - m2_bd) / den_m2) * 200.0) if den_m2 else 0.0
        return (r1 + r2) / 2.0

    def _dimrev_result_lines_vals(self):
        self.ensure_one()
        eval_rec = self.est_revirado_eval_id
        if not eval_rec:
            return []

        is_l1 = int(eval_rec.wash_number or 0) == 1
        ancho_pct = float(eval_rec.est_ancho_avg or 0.0)
        largo_pct = float(eval_rec.est_largo_avg or 0.0)
        revirado = float(eval_rec.revirado_promedio or 0.0)

        lines = [
            {"sequence": 10, "tipo": "%Ancho", "resultado": ancho_pct},
            {"sequence": 20, "tipo": "%Largo", "resultado": largo_pct},
            {"sequence": 30, "tipo": "Revirado", "resultado": revirado},
        ]
        if is_l1:
            lines += [
                {"sequence": 40, "tipo": "Densidad", "resultado": float(eval_rec.densidad_promedio or 0.0)},
                {"sequence": 50, "tipo": "Ancho", "resultado": float(eval_rec.ancho_promedio or 0.0)},
            ]
        return lines

    def _sync_result_lines(self):
        for rec in self:
            commands = [(5, 0, 0)]
            if rec.test_type == "dimrev":
                commands += [(0, 0, vals) for vals in rec._dimrev_result_lines_vals()]
            elif rec.test_type == "solidez_lavado":
                commands += [(0, 0, vals) for vals in rec._solidez_lavado_result_lines_vals()]
            rec.result_line_ids = commands

    def _solidez_lavado_result_lines_vals(self):
        self.ensure_one()
        eval_rec = self.solidez_lavado_eval_id
        if not eval_rec:
            return []

        return [
            {"sequence": 10, "tipo": "Cambio de color grado", "resultado": float(eval_rec.cambio_color_grado or 0.0)},
            {"sequence": 20, "tipo": "Migracion Acetato", "resultado": float(eval_rec.mig_acetato or 0.0)},
            {"sequence": 30, "tipo": "Migracion Algodon", "resultado": float(eval_rec.mig_algodon or 0.0)},
            {"sequence": 40, "tipo": "Migracion Nylon", "resultado": float(eval_rec.mig_nylon or 0.0)},
            {"sequence": 50, "tipo": "Migracion Poliester", "resultado": float(eval_rec.mig_poliester or 0.0)},
            {"sequence": 60, "tipo": "Migracion Acrilico", "resultado": float(eval_rec.mig_acrilico or 0.0)},
            {"sequence": 70, "tipo": "Migracion Lana", "resultado": float(eval_rec.mig_lana or 0.0)},
            {"sequence": 80, "tipo": "Frote Seco", "resultado": float(eval_rec.frote_seco or 0.0)},
            {"sequence": 90, "tipo": "Frote Humedo", "resultado": float(eval_rec.frote_humedo or 0.0)},
        ]

    @staticmethod
    def _has_measure_key(eval_rec, key):
        return any((line.measure_key or "") == key for line in eval_rec.detail_line_ids)

    def _dimrev_detect_wash(self, eval_rec):
        wash_number = int(eval_rec.wash_number or 0)
        if wash_number == 1:
            return ("l1", "1er Lavado")
        if wash_number == 3:
            return ("l3", "3er Lavado")
        if wash_number == 5:
            return ("l5", "5to Lavado")
        if wash_number > 0:
            return ("ln", f"Lavado N° {wash_number}")
        return ("l1", "1er Lavado")

    def _dimrev_first_eval_for_std(self):
        self.ensure_one()
        first_record = self.search([
            ("pedido_line_id", "=", self.pedido_line_id.id),
            ("test_type", "=", "dimrev"),
            ("est_revirado_eval_id", "!=", False),
        ], order="fecha_eval asc, id asc", limit=1)
        return first_record.est_revirado_eval_id if first_record else self.env["control.estabilidad.revirado.eval"]

    def _dimrev_report_payload(self):
        self.ensure_one()
        eval_rec = self.est_revirado_eval_id
        if not eval_rec:
            return {}

        wash_code, wash_label = self._dimrev_detect_wash(eval_rec)

        stability_rows = []
        for sample in (1, 2):
            stability_rows.append({
                "sample": f"M{sample}",
                "a_d1": eval_rec._get_measure_value(f"st_a_m{sample}_d1"),
                "a_d2": eval_rec._get_measure_value(f"st_a_m{sample}_d2"),
                "a_d3": eval_rec._get_measure_value(f"st_a_m{sample}_d3"),
                "l_d1": eval_rec._get_measure_value(f"st_l_m{sample}_d1"),
                "l_d2": eval_rec._get_measure_value(f"st_l_m{sample}_d2"),
                "l_d3": eval_rec._get_measure_value(f"st_l_m{sample}_d3"),
            })

        m1_ac = eval_rec._get_measure_value("rv_m1_ac")
        m1_bd = eval_rec._get_measure_value("rv_m1_bd")
        m2_ac = eval_rec._get_measure_value("rv_m2_ac")
        m2_bd = eval_rec._get_measure_value("rv_m2_bd")

        revirado_rows = [
            {
                "sample": "M1",
                "ac": m1_ac,
                "bd": m1_bd,
                "pct": (((m1_ac - m1_bd) / (m1_ac + m1_bd)) * 200.0) if (m1_ac + m1_bd) else 0.0,
            },
            {
                "sample": "M2",
                "ac": m2_ac,
                "bd": m2_bd,
                "pct": (((m2_ac - m2_bd) / (m2_ac + m2_bd)) * 200.0) if (m2_ac + m2_bd) else 0.0,
            },
        ]

        # Some assays do not capture STD values; fallback to the first dimrev assay for the same partida.
        source_eval = eval_rec
        has_std_data = self._has_measure_key(eval_rec, "den_1") and self._has_measure_key(eval_rec, "anc_1")
        if not has_std_data:
            source_eval = self._dimrev_first_eval_for_std() or eval_rec

        density_vals = [
            source_eval._get_measure_value("den_1") if source_eval else 0.0,
            source_eval._get_measure_value("den_2") if source_eval else 0.0,
            source_eval._get_measure_value("den_3") if source_eval else 0.0,
        ]
        width_vals = [
            source_eval._get_measure_value("anc_1") if source_eval else 0.0,
            source_eval._get_measure_value("anc_2") if source_eval else 0.0,
            source_eval._get_measure_value("anc_3") if source_eval else 0.0,
        ]
        density_avg = (sum(density_vals) / 3.0) if density_vals else 0.0
        width_avg = (sum(width_vals) / 3.0) if width_vals else 0.0

        est_ancho = self._wash_avg_from_details(eval_rec, "a")
        est_largo = self._wash_avg_from_details(eval_rec, "l")
        revirado_avg = self._revirado_promedio_from_values(m1_ac, m1_bd, m2_ac, m2_bd)

        thresholds = eval_rec.pedido_line_id.product_id.analysis_id.density_stability_twisting_id
        tilt_standard = float(thresholds.tilt_wash or 0.0) if thresholds else 0.0
        tilt_before = float(eval_rec._get_measure_value("tilt_before") or 0.0)
        tilt_after = float(eval_rec._get_measure_value("tilt_after") or 0.0)
        tilt_limit = tilt_standard + 1.0 if tilt_standard > 0.0 else 0.0

        tilt_before_status = "Sin estandar"
        if int(eval_rec.wash_number or 0) != 1:
            tilt_before_status = "No aplica"
        elif tilt_standard > 0.0:
            tilt_before_status = "Pasa" if tilt_before <= tilt_limit else "Falla"

        results = [
            {"tipo": "%Ancho", "resultado": est_ancho},
            {"tipo": "%Largo", "resultado": est_largo},
            {"tipo": "Revirado", "resultado": revirado_avg},
            {"tipo": "Densidad", "resultado": density_avg},
            {"tipo": "Ancho", "resultado": width_avg},
        ]
        if int(eval_rec.wash_number or 0) == 1:
            results.append({"tipo": "Inclinacion Antes de Lavar", "resultado": tilt_before})

        return {
            "wash_code": wash_code,
            "wash_label": wash_label,
            "stability_rows": stability_rows,
            "revirado_rows": revirado_rows,
            "density_vals": density_vals,
            "density_avg": density_avg,
            "width_vals": width_vals,
            "width_avg": width_avg,
            "tilt_before": tilt_before,
            "tilt_after": tilt_after,
            "tilt_standard": tilt_standard,
            "tilt_limit": tilt_limit,
            "tilt_before_status": tilt_before_status,
            "results": results,
            "std_source_label": "Ensayo actual" if source_eval == eval_rec else "Primer ensayo",
        }

    @api.depends("test_type", "est_revirado_eval_id", "est_revirado_eval_id.wash_number", "est_revirado_eval_id.detail_line_ids.measure_key")
    def _compute_numero_lavado(self):
        for rec in self:
            value = ""
            if rec.test_type == "dimrev" and rec.est_revirado_eval_id:
                wash_number = int(rec.est_revirado_eval_id.wash_number or 0)
                if wash_number == 1:
                    value = "1er Lavado"
                elif wash_number == 3:
                    value = "3er Lavado"
                elif wash_number == 5:
                    value = "5to Lavado"
                elif wash_number > 0:
                    value = f"Lavado N° {wash_number}"
            rec.numero_lavado = value

    def action_print_report(self):
        self.ensure_one()

        report_map = {
            "solidez_lavado": "idtx_batch_quality.action_report_solidez_lavado",
            "dimrev": "idtx_batch_quality.action_report_dimrev",
        }
        report_xmlid = report_map.get(self.test_type)
        if not report_xmlid:
            raise UserError(_("No hay reporte configurado para el tipo de prueba: %s") % (self.test_type or "-"))
        if self.test_type == "solidez_lavado" and not self.solidez_lavado_eval_id:
            raise UserError(_("Este registro no tiene evaluación de Solidez del Color al Lavado."))
        if self.test_type == "dimrev" and not self.est_revirado_eval_id:
            raise UserError(_("Este registro no tiene evaluación de Densidad + Estabilidad + Revirado."))

        return self.env.ref(report_xmlid).report_action(self)

class ControlLaboratorioRecordResult(models.Model):
    _name = "control.laboratorio.record.result"
    _description = "Resultado de Registro de Laboratorio"
    _order = "sequence asc, id asc"

    record_id = fields.Many2one("control.laboratorio.record", string="Registro", required=True, ondelete="cascade", index=True)
    sequence = fields.Integer(string="Secuencia", default=10, index=True)
    tipo = fields.Char(string="Tipo", required=True)
    resultado = fields.Float(string="Resultado", digits=(16, 4), required=True)
