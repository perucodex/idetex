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

    _sql_constraints = [
        (
            "uniq_laboratorio_eval_number",
            "unique(pedido_line_id, eval_number)",
            "El numero de evaluacion ya existe para esta partida.",
        ),
        (
            "uniq_dimrev_eval_link",
            "unique(est_revirado_eval_id)",
            "La evaluacion de estabilidad/revirado ya tiene un registro de laboratorio.",
        ),
        (
            "uniq_solidez_lavado_eval_link",
            "unique(solidez_lavado_eval_id)",
            "La evaluacion de solidez del color al lavado ya tiene un registro de laboratorio.",
        ),
    ]

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
    def _wash_avg_from_details(eval_rec, wash_code, axis):
        m1 = sum(eval_rec._get_measure_value(f"st_{wash_code}_{axis}_m1_d{d}") for d in (1, 2, 3)) / 3.0
        m2 = sum(eval_rec._get_measure_value(f"st_{wash_code}_{axis}_m2_d{d}") for d in (1, 2, 3)) / 3.0
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

        is_l1 = False
        if self._has_measure_prefix(eval_rec, "st_l5_"):
            ancho_pct = float(eval_rec.est_ancho_avg_l5 or 0.0)
            largo_pct = float(eval_rec.est_largo_avg_l5 or 0.0)
            revirado = self._revirado_promedio_from_values(
                eval_rec._get_measure_value("rv5_m1_ac"),
                eval_rec._get_measure_value("rv5_m1_bd"),
                eval_rec._get_measure_value("rv5_m2_ac"),
                eval_rec._get_measure_value("rv5_m2_bd"),
            )
        elif self._has_measure_prefix(eval_rec, "st_l3_"):
            ancho_pct = float(eval_rec.est_ancho_avg_l3 or 0.0)
            largo_pct = float(eval_rec.est_largo_avg_l3 or 0.0)
            revirado = self._revirado_promedio_from_values(
                eval_rec._get_measure_value("rv3_m1_ac"),
                eval_rec._get_measure_value("rv3_m1_bd"),
                eval_rec._get_measure_value("rv3_m2_ac"),
                eval_rec._get_measure_value("rv3_m2_bd"),
            )
        elif self._has_measure_prefix(eval_rec, "st_l1_"):
            is_l1 = True
            ancho_pct = float(eval_rec.est_ancho_avg_l1 or 0.0)
            largo_pct = float(eval_rec.est_largo_avg_l1 or 0.0)
            revirado = float(eval_rec.revirado_promedio or 0.0)
        elif self._has_measure_prefix(eval_rec, "st_ln_"):
            ancho_pct = self._wash_avg_from_details(eval_rec, "ln", "a")
            largo_pct = self._wash_avg_from_details(eval_rec, "ln", "l")
            revirado = float(eval_rec.revirado_n_promedio or 0.0)
        else:
            ancho_pct = 0.0
            largo_pct = 0.0
            revirado = 0.0

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
        if self._has_measure_prefix(eval_rec, "st_l1_"):
            return ("l1", "1er Lavado")
        if self._has_measure_prefix(eval_rec, "st_l3_"):
            return ("l3", "3er Lavado")
        if self._has_measure_prefix(eval_rec, "st_l5_"):
            return ("l5", "5to Lavado")
        if self._has_measure_prefix(eval_rec, "st_ln_"):
            n_value = int(eval_rec._get_measure_value("rvn_n") or 0)
            label = f"Lavado N° {n_value}" if n_value > 0 else "Lavado N"
            return ("ln", label)
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
                "a_d1": eval_rec._get_measure_value(f"st_{wash_code}_a_m{sample}_d1"),
                "a_d2": eval_rec._get_measure_value(f"st_{wash_code}_a_m{sample}_d2"),
                "a_d3": eval_rec._get_measure_value(f"st_{wash_code}_a_m{sample}_d3"),
                "l_d1": eval_rec._get_measure_value(f"st_{wash_code}_l_m{sample}_d1"),
                "l_d2": eval_rec._get_measure_value(f"st_{wash_code}_l_m{sample}_d2"),
                "l_d3": eval_rec._get_measure_value(f"st_{wash_code}_l_m{sample}_d3"),
            })

        revirado_key_by_wash = {
            "l1": ("rv1_m1_ac", "rv1_m1_bd", "rv1_m2_ac", "rv1_m2_bd"),
            "l3": ("rv3_m1_ac", "rv3_m1_bd", "rv3_m2_ac", "rv3_m2_bd"),
            "l5": ("rv5_m1_ac", "rv5_m1_bd", "rv5_m2_ac", "rv5_m2_bd"),
            "ln": ("rvn_m1_ac", "rvn_m1_bd", "rvn_m2_ac", "rvn_m2_bd"),
        }
        m1_ac_key, m1_bd_key, m2_ac_key, m2_bd_key = revirado_key_by_wash.get(wash_code, revirado_key_by_wash["l1"])
        m1_ac = eval_rec._get_measure_value(m1_ac_key)
        m1_bd = eval_rec._get_measure_value(m1_bd_key)
        m2_ac = eval_rec._get_measure_value(m2_ac_key)
        m2_bd = eval_rec._get_measure_value(m2_bd_key)

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

        est_ancho = self._wash_avg_from_details(eval_rec, wash_code, "a")
        est_largo = self._wash_avg_from_details(eval_rec, wash_code, "l")
        revirado_avg = self._revirado_promedio_from_values(m1_ac, m1_bd, m2_ac, m2_bd)

        results = [
            {"tipo": "%Ancho", "resultado": est_ancho},
            {"tipo": "%Largo", "resultado": est_largo},
            {"tipo": "Revirado", "resultado": revirado_avg},
            {"tipo": "Densidad", "resultado": density_avg},
            {"tipo": "Ancho", "resultado": width_avg},
        ]

        return {
            "wash_code": wash_code,
            "wash_label": wash_label,
            "stability_rows": stability_rows,
            "revirado_rows": revirado_rows,
            "density_vals": density_vals,
            "density_avg": density_avg,
            "width_vals": width_vals,
            "width_avg": width_avg,
            "results": results,
            "std_source_label": "Ensayo actual" if source_eval == eval_rec else "Primer ensayo",
        }

    @api.depends("test_type", "est_revirado_eval_id", "est_revirado_eval_id.detail_line_ids.measure_key")
    def _compute_numero_lavado(self):
        for rec in self:
            value = ""
            if rec.test_type == "dimrev" and rec.est_revirado_eval_id:
                eval_rec = rec.est_revirado_eval_id
                if self._has_measure_prefix(eval_rec, "st_l1_"):
                    value = "1ero Lavado"
                elif self._has_measure_prefix(eval_rec, "st_l3_"):
                    value = "3ero Lavado"
                elif self._has_measure_prefix(eval_rec, "st_l5_"):
                    value = "5to Lavado"
                elif self._has_measure_prefix(eval_rec, "st_ln_"):
                    n_value = int(eval_rec._get_measure_value("rvn_n") or 0)
                    value = f"Lavado N° {n_value}" if n_value > 0 else "Lavado N°"
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

    # Backward-compatible alias while view/action references are migrated.
    def action_print_solidez_lavado_report(self):
        return self.action_print_report()


class ControlLaboratorioRecordResult(models.Model):
    _name = "control.laboratorio.record.result"
    _description = "Resultado de Registro de Laboratorio"
    _order = "sequence asc, id asc"

    record_id = fields.Many2one("control.laboratorio.record", string="Registro", required=True, ondelete="cascade", index=True)
    sequence = fields.Integer(string="Secuencia", default=10, index=True)
    tipo = fields.Char(string="Tipo", required=True)
    resultado = fields.Float(string="Resultado", digits=(16, 4), required=True)
