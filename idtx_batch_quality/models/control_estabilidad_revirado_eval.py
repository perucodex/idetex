from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Domain


class ControlEstabilidadReviradoEval(models.Model):
    _name = "control.estabilidad.revirado.eval"
    _description = "Evaluacion Estabilidad Dimensional y Revirado"
    _order = "fecha_eval desc, id desc"

    _WASHES = ["l1", "l3", "l5"]

    name = fields.Char(string="Referencia", required=True, copy=False, default="New", index=True)
    fecha_eval = fields.Datetime(string="Fecha", required=True, default=fields.Datetime.now, index=True)
    user_id = fields.Many2one("res.users", string="Usuario", required=True, default=lambda self: self.env.user)
    pedido_line_id = fields.Many2one("control.pedido.line", string="Partida", required=True, ondelete="cascade", index=True)
    detail_line_ids = fields.One2many("control.estabilidad.revirado.eval.detail", "eval_id", string="Tabla de Datos", copy=False)

    est_l1_ancho_done = fields.Boolean(string="1er Lavado Ancho Completado", default=False)
    est_l1_largo_done = fields.Boolean(string="1er Lavado Largo Completado", default=False)
    est_l1_done = fields.Boolean(string="1er Lavado Completado", default=False)
    est_l3_ancho_done = fields.Boolean(string="3er Lavado Ancho Completado", default=False)
    est_l3_largo_done = fields.Boolean(string="3er Lavado Largo Completado", default=False)
    est_l3_done = fields.Boolean(string="3er Lavado Completado", default=False)
    est_l5_ancho_done = fields.Boolean(string="5to Lavado Ancho Completado", default=False)
    est_l5_largo_done = fields.Boolean(string="5to Lavado Largo Completado", default=False)
    est_l5_done = fields.Boolean(string="5to Lavado Completado", default=False)

    est_ancho_avg_l1 = fields.Float(string="% Ancho Promedio - 1er Lavado", compute="_compute_avgs", store=True)
    est_ancho_avg_l3 = fields.Float(string="% Ancho Promedio - 3er Lavado", compute="_compute_avgs", store=True)
    est_ancho_avg_l5 = fields.Float(string="% Ancho Promedio - 5to Lavado", compute="_compute_avgs", store=True)
    est_largo_avg_l1 = fields.Float(string="% Largo Promedio - 1er Lavado", compute="_compute_avgs", store=True)
    est_largo_avg_l3 = fields.Float(string="% Largo Promedio - 3er Lavado", compute="_compute_avgs", store=True)
    est_largo_avg_l5 = fields.Float(string="% Largo Promedio - 5to Lavado", compute="_compute_avgs", store=True)

    revirado_m1_result = fields.Float(string="Revirado M1", compute="_compute_revirado", store=True)
    revirado_m2_result = fields.Float(string="Revirado M2", compute="_compute_revirado", store=True)
    revirado_promedio = fields.Float(string="Revirado 1er Lavado Promedio", compute="_compute_revirado", store=True)
    revirado_n_lavado = fields.Integer(string="Lavado N", compute="_compute_revirado", store=True)
    revirado_n_m1_result = fields.Float(string="Revirado Lavado N M1", compute="_compute_revirado", store=True)
    revirado_n_m2_result = fields.Float(string="Revirado Lavado N M2", compute="_compute_revirado", store=True)
    revirado_n_promedio = fields.Float(string="Revirado Lavado N Promedio", compute="_compute_revirado", store=True)

    densidad_promedio = fields.Float(string="Densidad Promedio", compute="_compute_densidad_ancho", store=True)
    ancho_promedio = fields.Float(string="Ancho Promedio", compute="_compute_densidad_ancho", store=True)

    _sql_constraints = [
        ("uniq_pedido_line_eval", "unique(pedido_line_id)", "Ya existe una evaluacion para esta partida."),
    ]

    @api.model
    def _st_key(self, wash, axis, sample, datum):
        return f"st_{wash}_{axis}_m{sample}_d{datum}"

    @api.model
    def _detail_measure_map(self):
        result = {}
        seq = 10

        for wash in self._WASHES:
            wash_label = {"l1": "1er", "l3": "3er", "l5": "5to"}[wash]
            for axis, axis_label, prueba in (
                ("a", "% Ancho", f"est_{wash}_ancho"),
                ("l", "% Largo", f"est_{wash}_largo"),
            ):
                for sample in (1, 2):
                    for datum in (1, 2, 3):
                        key = self._st_key(wash, axis, sample, datum)
                        result[key] = {
                            "sequence": seq,
                            "prueba": prueba,
                            "muestra": f"m{sample}",
                            "evaluacion": f"{wash_label} Lavado {axis_label} D{datum}",
                        }
                        seq += 10

        for key, prueba, muestra, evaluacion in (
            ("rv1_m1_ac", "revirado_l1", "m1", "1er Lavado M1 AC"),
            ("rv1_m1_bd", "revirado_l1", "m1", "1er Lavado M1 BD"),
            ("rv1_m2_ac", "revirado_l1", "m2", "1er Lavado M2 AC"),
            ("rv1_m2_bd", "revirado_l1", "m2", "1er Lavado M2 BD"),
            ("rvn_n", "revirado_ln", "na", "Lavado N"),
            ("rvn_m1_ac", "revirado_ln", "m1", "Lavado N M1 AC"),
            ("rvn_m1_bd", "revirado_ln", "m1", "Lavado N M1 BD"),
            ("rvn_m2_ac", "revirado_ln", "m2", "Lavado N M2 AC"),
            ("rvn_m2_bd", "revirado_ln", "m2", "Lavado N M2 BD"),
            ("den_1", "densidad", "na", "Densidad Dato 1"),
            ("den_2", "densidad", "na", "Densidad Dato 2"),
            ("den_3", "densidad", "na", "Densidad Dato 3"),
            ("anc_1", "ancho", "na", "Ancho Dato 1"),
            ("anc_2", "ancho", "na", "Ancho Dato 2"),
            ("anc_3", "ancho", "na", "Ancho Dato 3"),
        ):
            result[key] = {
                "sequence": seq,
                "prueba": prueba,
                "muestra": muestra,
                "evaluacion": evaluacion,
            }
            seq += 10

        return result

    @api.model
    def _screen_fields(self):
        return list(self._detail_measure_map().keys())

    def _get_measure_value(self, key):
        self.ensure_one()
        line = self.detail_line_ids.filtered(lambda l: l.measure_key == key)[:1]
        return float(line.dato or 0.0) if line else 0.0

    def _get_measure_values(self):
        self.ensure_one()
        values = {key: 0.0 for key in self._screen_fields()}
        for line in self.detail_line_ids:
            if line.measure_key in values:
                values[line.measure_key] = float(line.dato or 0.0)
        return values

    def _upsert_measure_value(self, key, value):
        self.ensure_one()
        meta = self._detail_measure_map().get(key)
        if not meta:
            return
        line = self.detail_line_ids.filtered(lambda l: l.measure_key == key)[:1]
        vals = {
            "sequence": meta["sequence"],
            "measure_key": key,
            "prueba": meta["prueba"],
            "muestra": meta["muestra"],
            "evaluacion": meta["evaluacion"],
            "dato": float(value or 0.0),
        }
        if line:
            line.write(vals)
        else:
            self.env["control.estabilidad.revirado.eval.detail"].create(dict(vals, eval_id=self.id))

    def _wash_avg(self, wash, axis):
        self.ensure_one()
        m1 = sum(self._get_measure_value(self._st_key(wash, axis, 1, d)) for d in (1, 2, 3)) / 3.0
        m2 = sum(self._get_measure_value(self._st_key(wash, axis, 2, d)) for d in (1, 2, 3)) / 3.0
        return (m1 + m2) / 2.0

    @api.depends("detail_line_ids.dato", "detail_line_ids.measure_key")
    def _compute_avgs(self):
        for rec in self:
            rec.est_ancho_avg_l1 = rec._wash_avg("l1", "a")
            rec.est_ancho_avg_l3 = rec._wash_avg("l3", "a")
            rec.est_ancho_avg_l5 = rec._wash_avg("l5", "a")
            rec.est_largo_avg_l1 = rec._wash_avg("l1", "l")
            rec.est_largo_avg_l3 = rec._wash_avg("l3", "l")
            rec.est_largo_avg_l5 = rec._wash_avg("l5", "l")

    @api.depends("detail_line_ids.dato", "detail_line_ids.measure_key")
    def _compute_revirado(self):
        for rec in self:
            m1_ac = rec._get_measure_value("rv1_m1_ac")
            m1_bd = rec._get_measure_value("rv1_m1_bd")
            m2_ac = rec._get_measure_value("rv1_m2_ac")
            m2_bd = rec._get_measure_value("rv1_m2_bd")
            den_m1 = m1_ac + m1_bd
            den_m2 = m2_ac + m2_bd
            rec.revirado_m1_result = (((m1_ac - m1_bd) / den_m1) * 200.0) if den_m1 else 0.0
            rec.revirado_m2_result = (((m2_ac - m2_bd) / den_m2) * 200.0) if den_m2 else 0.0
            rec.revirado_promedio = (rec.revirado_m1_result + rec.revirado_m2_result) / 2.0

            rec.revirado_n_lavado = int(rec._get_measure_value("rvn_n") or 0)
            n_m1_ac = rec._get_measure_value("rvn_m1_ac")
            n_m1_bd = rec._get_measure_value("rvn_m1_bd")
            n_m2_ac = rec._get_measure_value("rvn_m2_ac")
            n_m2_bd = rec._get_measure_value("rvn_m2_bd")
            den_n_m1 = n_m1_ac + n_m1_bd
            den_n_m2 = n_m2_ac + n_m2_bd
            rec.revirado_n_m1_result = (((n_m1_ac - n_m1_bd) / den_n_m1) * 200.0) if den_n_m1 else 0.0
            rec.revirado_n_m2_result = (((n_m2_ac - n_m2_bd) / den_n_m2) * 200.0) if den_n_m2 else 0.0
            rec.revirado_n_promedio = (rec.revirado_n_m1_result + rec.revirado_n_m2_result) / 2.0

    @api.depends("detail_line_ids.dato", "detail_line_ids.measure_key")
    def _compute_densidad_ancho(self):
        for rec in self:
            rec.densidad_promedio = (rec._get_measure_value("den_1") + rec._get_measure_value("den_2") + rec._get_measure_value("den_3")) / 3.0
            rec.ancho_promedio = (rec._get_measure_value("anc_1") + rec._get_measure_value("anc_2") + rec._get_measure_value("anc_3")) / 3.0

    @api.model_create_multi
    def create(self, vals_list):
        seq = self.env["ir.sequence"]
        for vals in vals_list:
            if vals.get("name", "New") == "New":
                vals["name"] = seq.next_by_code("control.estabilidad.revirado.eval") or "New"
        return super().create(vals_list)

    @staticmethod
    def _step_fields(step_key):
        map_steps = {
            "est_l1_ancho": [f"st_l1_a_m{s}_d{d}" for s in (1, 2) for d in (1, 2, 3)],
            "est_l1_largo": [f"st_l1_l_m{s}_d{d}" for s in (1, 2) for d in (1, 2, 3)],
            "est_l3_ancho": [f"st_l3_a_m{s}_d{d}" for s in (1, 2) for d in (1, 2, 3)],
            "est_l3_largo": [f"st_l3_l_m{s}_d{d}" for s in (1, 2) for d in (1, 2, 3)],
            "est_l5_ancho": [f"st_l5_a_m{s}_d{d}" for s in (1, 2) for d in (1, 2, 3)],
            "est_l5_largo": [f"st_l5_l_m{s}_d{d}" for s in (1, 2) for d in (1, 2, 3)],
            "revirado_l1": ["rv1_m1_ac", "rv1_m1_bd", "rv1_m2_ac", "rv1_m2_bd"],
            "revirado_ln": ["rvn_n", "rvn_m1_ac", "rvn_m1_bd", "rvn_m2_ac", "rvn_m2_bd"],
            "densidad": ["den_1", "den_2", "den_3"],
            "ancho": ["anc_1", "anc_2", "anc_3"],
        }
        return map_steps.get(step_key, [])

    def _check_stability_sequence(self, step_key):
        self.ensure_one()
        if step_key == "est_l1_ancho":
            return
        if step_key == "est_l1_largo" and not self.est_l1_ancho_done:
            raise UserError(_("Primero debe registrar el % Ancho del 1er lavado para esta partida."))
        if step_key == "est_l3_ancho" and not self.est_l1_done:
            raise UserError(_("Primero debe completar el 1er lavado para esta partida."))
        if step_key == "est_l3_largo" and not self.est_l3_ancho_done:
            raise UserError(_("Primero debe registrar el % Ancho del 3er lavado para esta partida."))
        if step_key == "est_l5_ancho" and not self.est_l3_done:
            raise UserError(_("Primero debe completar el 3er lavado para esta partida."))
        if step_key == "est_l5_largo" and not self.est_l5_ancho_done:
            raise UserError(_("Primero debe registrar el % Ancho del 5to lavado para esta partida."))

    def _to_tablet_payload(self):
        self.ensure_one()
        return {
            "id": self.id,
            "name": self.name,
            "pedido_line_id": self.pedido_line_id.id,
            "values": self._get_measure_values(),
            "stability": {
                "l1_ancho_done": bool(self.est_l1_ancho_done),
                "l1_largo_done": bool(self.est_l1_largo_done),
                "l1_done": bool(self.est_l1_done),
                "l3_ancho_done": bool(self.est_l3_ancho_done),
                "l3_largo_done": bool(self.est_l3_largo_done),
                "l3_done": bool(self.est_l3_done),
                "l5_ancho_done": bool(self.est_l5_ancho_done),
                "l5_largo_done": bool(self.est_l5_largo_done),
                "l5_done": bool(self.est_l5_done),
            },
        }

    @api.model
    def action_tablet_get_or_create(self, pedido_line_id):
        pedido_line = self.env["control.pedido.line"].browse(int(pedido_line_id or 0))
        if not pedido_line.exists():
            raise UserError(_("Seleccione una partida valida."))
        rec = self.search([("pedido_line_id", "=", pedido_line.id)], limit=1)
        if not rec:
            rec = self.create({"pedido_line_id": pedido_line.id, "user_id": self.env.user.id})
        return rec._to_tablet_payload()

    @api.model
    def action_tablet_get_partidas(self, query="", limit=50):
        query = (query or "").strip()
        domain = Domain([])
        if query:
            terms = [term.strip() for term in query.split(",") if term.strip()] or [query]
            domain = Domain.AND([
                Domain.OR([
                    Domain("batch", "ilike", term),
                    Domain("pedido_id.customer", "ilike", term),
                    Domain("description", "ilike", term),
                    Domain("colorname", "ilike", term),
                    Domain("colorcode", "ilike", term),
                ])
                for term in terms
            ])

        safe_limit = min(max(int(limit or 50), 1), 300)
        lines = self.env["control.pedido.line"].search(domain, order="batch desc, id desc", limit=safe_limit)
        return [{
            "id": line.id,
            "label": f"{line.batch or '-'} | {line.pedido_id.customer or '-'}",
            "batch": line.batch or "",
            "customer": line.pedido_id.customer or "",
            "article": line.description or "",
            "color_name": line.colorname or "",
            "color_code": line.colorcode or "",
            "kilograms": float(line.kilograms or 0.0),
        } for line in lines]

    @api.model
    def action_tablet_submit_step(self, pedido_line_id, step_key, values):
        pedido_line = self.env["control.pedido.line"].browse(int(pedido_line_id or 0))
        if not pedido_line.exists():
            raise UserError(_("Seleccione una partida valida."))

        fields_for_step = self._step_fields((step_key or "").strip())
        if not fields_for_step:
            raise UserError(_("Paso de evaluacion invalido."))

        rec = self.search([("pedido_line_id", "=", pedido_line.id)], limit=1)
        if not rec:
            rec = self.create({"pedido_line_id": pedido_line.id, "user_id": self.env.user.id})

        rec._check_stability_sequence(step_key)

        for fname in fields_for_step:
            raw = (values or {}).get(fname, 0.0)
            try:
                value = int(float(raw or 0.0)) if fname == "rvn_n" else float(raw or 0.0)
            except (TypeError, ValueError):
                raise UserError(_("El valor de %s no es numerico.") % fname)
            rec._upsert_measure_value(fname, value)

        if step_key == "revirado_ln" and int(rec._get_measure_value("rvn_n") or 0) < 2:
            raise UserError(_("El lavado N debe ser mayor o igual a 2."))

        write_vals = {}
        if step_key == "est_l1_ancho":
            write_vals["est_l1_ancho_done"] = True
        elif step_key == "est_l1_largo":
            write_vals.update({"est_l1_largo_done": True, "est_l1_done": True})
        elif step_key == "est_l3_ancho":
            write_vals["est_l3_ancho_done"] = True
        elif step_key == "est_l3_largo":
            write_vals.update({"est_l3_largo_done": True, "est_l3_done": True})
        elif step_key == "est_l5_ancho":
            write_vals["est_l5_ancho_done"] = True
        elif step_key == "est_l5_largo":
            write_vals.update({"est_l5_largo_done": True, "est_l5_done": True})

        if write_vals:
            rec.write(write_vals)

        return {
            "ok": True,
            "id": rec.id,
            "name": rec.name,
            "stability": {
                "l1_ancho_done": bool(rec.est_l1_ancho_done),
                "l1_largo_done": bool(rec.est_l1_largo_done),
                "l1_done": bool(rec.est_l1_done),
                "l3_ancho_done": bool(rec.est_l3_ancho_done),
                "l3_largo_done": bool(rec.est_l3_largo_done),
                "l3_done": bool(rec.est_l3_done),
                "l5_ancho_done": bool(rec.est_l5_ancho_done),
                "l5_largo_done": bool(rec.est_l5_largo_done),
                "l5_done": bool(rec.est_l5_done),
            },
        }


class ControlEstabilidadReviradoEvalDetail(models.Model):
    _name = "control.estabilidad.revirado.eval.detail"
    _description = "Detalle de Evaluacion Estabilidad/Revirado"
    _order = "sequence asc, id asc"

    eval_id = fields.Many2one("control.estabilidad.revirado.eval", string="Evaluacion", required=True, ondelete="cascade", index=True)
    sequence = fields.Integer(string="Secuencia", default=10, index=True)
    measure_key = fields.Char(string="Clave", required=True, index=True)
    prueba = fields.Selection([
        ("est_l1_ancho", "Estabilidad 1er Lavado % Ancho"),
        ("est_l1_largo", "Estabilidad 1er Lavado % Largo"),
        ("est_l3_ancho", "Estabilidad 3er Lavado % Ancho"),
        ("est_l3_largo", "Estabilidad 3er Lavado % Largo"),
        ("est_l5_ancho", "Estabilidad 5to Lavado % Ancho"),
        ("est_l5_largo", "Estabilidad 5to Lavado % Largo"),
        ("revirado_l1", "Revirado 1er Lavado"),
        ("revirado_ln", "Revirado Lavado N"),
        ("densidad", "Densidad"),
        ("ancho", "Ancho"),
    ], string="Prueba", required=True, index=True)
    muestra = fields.Selection([("m1", "M1"), ("m2", "M2"), ("na", "N/A")], string="Muestra", default="na", required=True, index=True)
    evaluacion = fields.Char(string="Evaluacion", required=True)
    dato = fields.Float(string="Dato", digits=(16, 4), required=True)

    _sql_constraints = [
        ("uniq_eval_measure_key", "unique(eval_id, measure_key)", "La clave de medicion ya existe en esta evaluacion."),
    ]
