import re

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Domain


class ControlEstabilidadReviradoEval(models.Model):
    _name = "qc.dimstab.eval"
    _description = "Evaluacion Estabilidad Dimensional y Revirado"
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = "fecha_eval desc, id desc"

    _MODE_STEP_KEYS = {
        "l1": ("est_l1_m1", "est_l1_m2", "densidad", "ancho"),
        "l3": ("est_l3_m1", "est_l3_m2"),
        "l5": ("est_l5_m1", "est_l5_m2"),
        "ln": ("est_ln_m1", "est_ln_m2"),
    }
    _WASH_NUMBER_BY_MODE = {
        "l1": 1,
        "l3": 3,
        "l5": 5,
    }
    _SAMPLE_TYPE_SELECTION = [
        ("seco_ppe", "Seco PPE"),
        ("empastado_digital", "Empastado Digital"),
        ("seco_estampado_rama", "Seco Estampado Rama"),
        ("acabado", "Acabado"),
        ("sanforizado_compactado", "Sanforizado y Compactado"),
        ("estampado", "Estampado"),
    ]
    _CANONICAL_KEYS = {
        "st_a_m1_d1", "st_a_m1_d2", "st_a_m1_d3",
        "st_a_m2_d1", "st_a_m2_d2", "st_a_m2_d3",
        "st_l_m1_d1", "st_l_m1_d2", "st_l_m1_d3",
        "st_l_m2_d1", "st_l_m2_d2", "st_l_m2_d3",
        "rv_m1_ac", "rv_m1_bd", "rv_m2_ac", "rv_m2_bd",
        "tilt_before_m1", "tilt_before_m2", "tilt_after_m1", "tilt_after_m2",
        "tilt_before_dir_m1", "tilt_before_dir_m2", "tilt_after_dir_m1", "tilt_after_dir_m2",
        "den_1", "den_2", "den_3",
        "anc_1", "anc_2", "anc_3",
    }

    name = fields.Char(string="Referencia", required=True, copy=False, default="New", index=True)
    fecha_eval = fields.Datetime(string="Fecha", required=True, default=fields.Datetime.now, index=True)
    sample_type = fields.Selection(_SAMPLE_TYPE_SELECTION, string="Tipo de Muestra", required=True, default="acabado", index=True)
    wash_number = fields.Integer(string="Numero de Lavado", required=True, default=1, index=True)
    user_ids = fields.Many2many(
        "res.users",
        "qc_dimstab_eval_res_users_rel",
        "eval_id",
        "user_id",
        string="Usuarios",
        default=lambda self: [(6, 0, [self.env.user.id])],
    )
    batch_id = fields.Many2one("mrp.workorder.batch", string="Partida", required=True, ondelete="cascade", index=True)
    detail_line_ids = fields.One2many("qc.dimstab.eval.detail", "eval_id", string="Tabla de Datos", copy=False)

    est_l1_ancho_done = fields.Boolean(string="1er Lavado Ancho Completado", default=False)
    est_l1_largo_done = fields.Boolean(string="1er Lavado Largo Completado", default=False)
    est_l1_done = fields.Boolean(string="1er Lavado Completado", default=False)
    est_l3_ancho_done = fields.Boolean(string="3er Lavado Ancho Completado", default=False)
    est_l3_largo_done = fields.Boolean(string="3er Lavado Largo Completado", default=False)
    est_l3_done = fields.Boolean(string="3er Lavado Completado", default=False)
    est_l5_ancho_done = fields.Boolean(string="5to Lavado Ancho Completado", default=False)
    est_l5_largo_done = fields.Boolean(string="5to Lavado Largo Completado", default=False)
    est_l5_done = fields.Boolean(string="5to Lavado Completado", default=False)

    est_ancho_avg = fields.Float(string="% Ancho Promedio", compute="_compute_avgs", store=True, digits=(16, 1))
    est_largo_avg = fields.Float(string="% Largo Promedio", compute="_compute_avgs", store=True, digits=(16, 1))

    revirado_m1_result = fields.Float(string="Revirado M1", compute="_compute_revirado", store=True, digits=(16, 1))
    revirado_m2_result = fields.Float(string="Revirado M2", compute="_compute_revirado", store=True, digits=(16, 1))
    revirado_promedio = fields.Float(string="Revirado Promedio", compute="_compute_revirado", store=True, digits=(16, 1))
    tilt_before = fields.Float(string="Inclinacion Antes de Lavar", compute="_compute_tilt", store=True, digits=(16, 1))
    tilt_after = fields.Float(string="Inclinacion Despues de Lavar", compute="_compute_tilt", store=True, digits=(16, 1))
    tilt_before_m1 = fields.Float(string="Inclinacion Antes de Lavar M1", compute="_compute_tilt", store=True, digits=(16, 1))
    tilt_before_m2 = fields.Float(string="Inclinacion Antes de Lavar M2", compute="_compute_tilt", store=True, digits=(16, 1))
    tilt_after_m1 = fields.Float(string="Inclinacion Despues de Lavar M1", compute="_compute_tilt", store=True, digits=(16, 1))
    tilt_after_m2 = fields.Float(string="Inclinacion Despues de Lavar M2", compute="_compute_tilt", store=True, digits=(16, 1))
    tilt_before_dir_m1 = fields.Selection([("z", "Z"), ("s", "S")], string="Sentido Antes M1", compute="_compute_tilt", store=True)
    tilt_before_dir_m2 = fields.Selection([("z", "Z"), ("s", "S")], string="Sentido Antes M2", compute="_compute_tilt", store=True)
    tilt_after_dir_m1 = fields.Selection([("z", "Z"), ("s", "S")], string="Sentido Despues M1", compute="_compute_tilt", store=True)
    tilt_after_dir_m2 = fields.Selection([("z", "Z"), ("s", "S")], string="Sentido Despues M2", compute="_compute_tilt", store=True)

    densidad_promedio = fields.Float(string="Densidad Promedio", compute="_compute_densidad_ancho", store=True, digits=(16, 1))
    ancho_promedio = fields.Float(string="Ancho Promedio", compute="_compute_densidad_ancho", store=True, digits=(16, 1))

    bool_est_ancho_avg = fields.Boolean()
    bool_est_largo_avg = fields.Boolean()
    bool_revirado_promedio = fields.Boolean()
    bool_tilt_before = fields.Boolean()
    bool_densidad_promedio = fields.Boolean()
    bool_ancho_promedio = fields.Boolean()
    criteria_force_pass = fields.Boolean(string="Forzar Pass por Criterio", default=False)
    repeat_kind = fields.Selection(
        [
            ("original", "Original"),
            ("reproceso", "Reproceso"),
            ("test", "Test"),
        ],
        string="Tipo de Repeticion",
        default="original",
        required=True,
        index=True,
        tracking=True,
        help="Original: primera evaluacion del lavado. Reproceso: repeticion oficial que "
             "reemplaza el resultado. Test: repeticion no oficial, no afecta el resultado.",
    )

    state = fields.Selection([
        ('pass', 'Pass'),
        ('fail', 'Fail'),
        ('nodata', 'No Data'),
    ], string='Resultado', compute='_compute_result_state', store=True, tracking=True)

    @staticmethod
    def _wash_code_from_number(wash_number):
        if int(wash_number or 0) == 1:
            return "l1"
        if int(wash_number or 0) == 3:
            return "l3"
        if int(wash_number or 0) == 5:
            return "l5"
        return "ln"

    @staticmethod
    def _wash_label_from_number(wash_number):
        number = int(wash_number or 0)
        if number == 1:
            return "1er Lavado"
        if number == 3:
            return "3er Lavado"
        if number == 5:
            return "5to Lavado"
        if number > 0:
            return f"Lavado {number}"
        return "Lavado"

    @classmethod
    def _canonical_from_input_key(cls, key):
        if not key:
            return None
        if key in cls._CANONICAL_KEYS:
            return key
        if key == "rvn_n":
            return None

        st_match = re.match(r"^st_(l1|l3|l5|ln)_([al])_m([12])_d([123])$", key)
        if st_match:
            _, axis, sample, datum = st_match.groups()
            return f"st_{axis}_m{sample}_d{datum}"

        rv_match = re.match(r"^rv(?:1|3|5|n)_m([12])_(ac|bd)$", key)
        if rv_match:
            sample, side = rv_match.groups()
            return f"rv_m{sample}_{side}"

        if key in {"den_1", "den_2", "den_3", "anc_1", "anc_2", "anc_3"}:
            return key
        return key

    @classmethod
    def _screen_key_from_canonical(cls, canonical_key, wash_number):
        wash_code = cls._wash_code_from_number(wash_number)

        st_match = re.match(r"^st_([al])_m([12])_d([123])$", canonical_key or "")
        if st_match:
            axis, sample, datum = st_match.groups()
            return f"st_{wash_code}_{axis}_m{sample}_d{datum}"

        rv_match = re.match(r"^rv_m([12])_(ac|bd)$", canonical_key or "")
        if rv_match:
            sample, side = rv_match.groups()
            prefix = {"l1": "rv1", "l3": "rv3", "l5": "rv5", "ln": "rvn"}[wash_code]
            return f"{prefix}_m{sample}_{side}"

        return canonical_key

    @classmethod
    def _lookup_keys_for_query(cls, query_key, wash_number):
        keys = []
        canonical = cls._canonical_from_input_key(query_key)
        wash_code = cls._wash_code_from_number(wash_number)

        if canonical:
            keys.append(canonical)

            st_match = re.match(r"^st_([al])_m([12])_d([123])$", canonical)
            if st_match:
                axis, sample, datum = st_match.groups()
                keys.append(f"st_{wash_code}_{axis}_m{sample}_d{datum}")

            rv_match = re.match(r"^rv_m([12])_(ac|bd)$", canonical)
            if rv_match:
                sample, side = rv_match.groups()
                prefix = {"l1": "rv1", "l3": "rv3", "l5": "rv5", "ln": "rvn"}[wash_code]
                keys.append(f"{prefix}_m{sample}_{side}")

        if query_key and query_key not in keys:
            keys.append(query_key)

        # Preserve order and uniqueness.
        return list(dict.fromkeys(keys))

    def _detail_measure_map(self):
        result = {}
        seq = 10

        self.ensure_one()
        wash_label = self._wash_label_from_number(self.wash_number)

        for axis, axis_label in (
            ("a", "% Ancho"),
            ("l", "% Largo"),
        ):
            for sample in (1, 2):
                for datum in (1, 2, 3):
                    key = f"st_{axis}_m{sample}_d{datum}"
                    result[key] = {
                        "sequence": seq,
                        "muestra": f"m{sample}",
                        "evaluacion": f"Estabilidad {wash_label} {axis_label} D{datum}",
                    }
                    seq += 10

        for key, muestra, evaluacion in (
            ("rv_m1_ac", "m1", f"Revirado {wash_label} M1 AC"),
            ("rv_m1_bd", "m1", f"Revirado {wash_label} M1 BD"),
            ("rv_m2_ac", "m2", f"Revirado {wash_label} M2 AC"),
            ("rv_m2_bd", "m2", f"Revirado {wash_label} M2 BD"),
            ("tilt_before_m1", "m1", "Inclinacion Antes de Lavar M1"),
            ("tilt_before_m2", "m2", "Inclinacion Antes de Lavar M2"),
            ("tilt_after_m1", "m1", "Inclinacion Despues de Lavar M1"),
            ("tilt_after_m2", "m2", "Inclinacion Despues de Lavar M2"),
            ("tilt_before_dir_m1", "m1", "Sentido Inclinacion Antes M1"),
            ("tilt_before_dir_m2", "m2", "Sentido Inclinacion Antes M2"),
            ("tilt_after_dir_m1", "m1", "Sentido Inclinacion Despues M1"),
            ("tilt_after_dir_m2", "m2", "Sentido Inclinacion Despues M2"),
            ("den_1", "na", "Densidad Dato 1"),
            ("den_2", "na", "Densidad Dato 2"),
            ("den_3", "na", "Densidad Dato 3"),
            ("anc_1", "na", "Ancho Dato 1"),
            ("anc_2", "na", "Ancho Dato 2"),
            ("anc_3", "na", "Ancho Dato 3"),
        ):
            result[key] = {
                "sequence": seq,
                "muestra": muestra,
                "evaluacion": evaluacion,
            }
            seq += 10

        return result

    @api.model
    def _screen_fields(self):
        fields = []
        for wash in ("l1", "l3", "l5", "ln"):
            for axis in ("a", "l"):
                for sample in (1, 2):
                    for datum in (1, 2, 3):
                        fields.append(f"st_{wash}_{axis}_m{sample}_d{datum}")
        fields.extend([
            "rv1_m1_ac", "rv1_m1_bd", "rv1_m2_ac", "rv1_m2_bd",
            "rv3_m1_ac", "rv3_m1_bd", "rv3_m2_ac", "rv3_m2_bd",
            "rv5_m1_ac", "rv5_m1_bd", "rv5_m2_ac", "rv5_m2_bd",
            "rvn_n", "rvn_m1_ac", "rvn_m1_bd", "rvn_m2_ac", "rvn_m2_bd",
            "tilt_before_m1", "tilt_before_m2", "tilt_after_m1", "tilt_after_m2",
            "tilt_before_dir_m1", "tilt_before_dir_m2", "tilt_after_dir_m1", "tilt_after_dir_m2",
            "den_1", "den_2", "den_3", "anc_1", "anc_2", "anc_3",
        ])
        return fields

    def _get_measure_value(self, key):
        self.ensure_one()
        for lookup_key in self._lookup_keys_for_query(key, self.wash_number):
            line = self.detail_line_ids.filtered(lambda l: l.measure_key == lookup_key)[:1]
            if line:
                return float(line.dato or 0.0)
        return 0.0

    def _get_measure_values(self):
        self.ensure_one()
        values = {key: 0.0 for key in self._screen_fields()}
        values["rvn_n"] = float(self.wash_number or 0)
        for line in self.detail_line_ids:
            if line.measure_key in values:
                values[line.measure_key] = float(line.dato or 0.0)
                continue

            screen_key = self._screen_key_from_canonical(line.measure_key, self.wash_number)
            if screen_key in values:
                values[screen_key] = float(line.dato or 0.0)
        return values

    def _upsert_measure_value(self, key, value):
        self.ensure_one()
        canonical_key = self._canonical_from_input_key(key)
        if not canonical_key:
            return

        # Densidad y ancho solo se almacenan en el primer lavado.
        if canonical_key.startswith(("den_", "anc_")) and int(self.wash_number or 0) != 1:
            return
        # Inclinacion antes de lavar solo se almacena en 1er lavado.
        if canonical_key.startswith("tilt_before") and int(self.wash_number or 0) != 1:
            return

        meta = self._detail_measure_map().get(canonical_key)
        if not meta:
            return
        line = self.detail_line_ids.filtered(lambda l: l.measure_key == canonical_key)[:1]
        numeric_value = float(value or 0.0)
        # Un solo decimal en todas las mediciones. Las claves de sentido
        # (tilt_*_dir_*) guardan +/-1 y el redondeo no las altera.
        if not (canonical_key.startswith("tilt_") and "_dir_" in canonical_key):
            numeric_value = round(numeric_value, 1)
        vals = {
            "sequence": meta["sequence"],
            "measure_key": canonical_key,
            "muestra": meta["muestra"],
            "evaluacion": meta["evaluacion"],
            "dato": numeric_value,
        }
        if line:
            write_vals = {}

            # Keep metadata aligned, but do not change audit fields unless value changed.
            for field_name in ("sequence", "measure_key", "muestra", "evaluacion"):
                if line[field_name] != vals[field_name]:
                    write_vals[field_name] = vals[field_name]

            if abs(float(line.dato or 0.0) - numeric_value) > 1e-9:
                write_vals.update({
                    "dato": numeric_value,
                    "user_id": self.env.user.id,
                    "fecha_registro": fields.Datetime.now(),
                })

            if write_vals:
                line.write(write_vals)
        else:
            self.env["qc.dimstab.eval.detail"].create(dict(
                vals,
                eval_id=self.id,
                user_id=self.env.user.id,
                fecha_registro=fields.Datetime.now(),
            ))

    def _wash_avg(self, axis):
        self.ensure_one()
        m1 = sum(self._get_measure_value(f"st_{axis}_m1_d{d}") for d in (1, 2, 3)) / 3.0
        m2 = sum(self._get_measure_value(f"st_{axis}_m2_d{d}") for d in (1, 2, 3)) / 3.0
        return (m1 + m2) / 2.0

    @api.depends("detail_line_ids.dato", "detail_line_ids.measure_key")
    def _compute_avgs(self):
        for rec in self:
            rec.est_ancho_avg = rec._wash_avg("a")
            rec.est_largo_avg = rec._wash_avg("l")

    @api.depends("detail_line_ids.dato", "detail_line_ids.measure_key")
    def _compute_revirado(self):
        for rec in self:
            m1_ac = rec._get_measure_value("rv_m1_ac")
            m1_bd = rec._get_measure_value("rv_m1_bd")
            m2_ac = rec._get_measure_value("rv_m2_ac")
            m2_bd = rec._get_measure_value("rv_m2_bd")
            den_m1 = m1_ac + m1_bd
            den_m2 = m2_ac + m2_bd
            rec.revirado_m1_result = (((m1_ac - m1_bd) / den_m1) * 200.0) if den_m1 else 0.0
            rec.revirado_m2_result = (((m2_ac - m2_bd) / den_m2) * 200.0) if den_m2 else 0.0
            if den_m1 > 0 and den_m2 > 0:
                rec.revirado_promedio = (rec.revirado_m1_result + rec.revirado_m2_result) / 2.0
            elif den_m1 > 0:
                rec.revirado_promedio = rec.revirado_m1_result
            elif den_m2 > 0:
                rec.revirado_promedio = rec.revirado_m2_result
            else:
                rec.revirado_promedio = 0.0

    @api.depends("detail_line_ids.dato", "detail_line_ids.measure_key")
    def _compute_tilt(self):
        for rec in self:
            before_m1 = float(rec._get_measure_value("tilt_before_m1") or 0.0)
            before_m2 = float(rec._get_measure_value("tilt_before_m2") or 0.0)
            after_m1 = float(rec._get_measure_value("tilt_after_m1") or 0.0)
            after_m2 = float(rec._get_measure_value("tilt_after_m2") or 0.0)

            rec.tilt_before_m1 = before_m1
            rec.tilt_before_m2 = before_m2
            rec.tilt_after_m1 = after_m1
            rec.tilt_after_m2 = after_m2

            rec.tilt_before = (before_m1 + before_m2) / 2.0 if (rec._has_measure_value("tilt_before_m1") and rec._has_measure_value("tilt_before_m2")) else 0.0
            rec.tilt_after = (after_m1 + after_m2) / 2.0 if (rec._has_measure_value("tilt_after_m1") and rec._has_measure_value("tilt_after_m2")) else 0.0

            rec.tilt_before_dir_m1 = "s" if float(rec._get_measure_value("tilt_before_dir_m1") or 1.0) < 0 else "z"
            rec.tilt_before_dir_m2 = "s" if float(rec._get_measure_value("tilt_before_dir_m2") or 1.0) < 0 else "z"
            rec.tilt_after_dir_m1 = "s" if float(rec._get_measure_value("tilt_after_dir_m1") or 1.0) < 0 else "z"
            rec.tilt_after_dir_m2 = "s" if float(rec._get_measure_value("tilt_after_dir_m2") or 1.0) < 0 else "z"

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
                vals["name"] = seq.next_by_code("qc.dimstab.eval") or "New"
            vals.setdefault("wash_number", 1)
            vals.setdefault("sample_type", "acabado")
            if not vals.get("user_ids"):
                vals["user_ids"] = [(6, 0, [self.env.user.id])]
        records = super().create(vals_list)

        laboratorio_model = self.env["qc.lab.record"]
        for rec in records:
            if not rec.batch_id:
                continue
            # Un "test" es una repeticion NO oficial: no genera registro de
            # laboratorio ni afecta el resultado de la partida.
            if rec.repeat_kind == "test":
                continue
            exists = laboratorio_model.search([("est_revirado_eval_id", "=", rec.id)], limit=1)
            if exists:
                continue
            first_user = rec.user_ids[:1] or self.env.user
            laboratorio_model.create({
                "batch_id": rec.batch_id.id,
                "fecha_eval": rec.fecha_eval,
                "user_id": first_user.id,
                "test_type": "dimrev",
                "result_state": "uncomplete",
                "est_revirado_eval_id": rec.id,
            })
        return records

    @staticmethod
    def _step_fields(step_key):
        map_steps = {
            "est_l1_m1": [
                "st_l1_a_m1_d1", "st_l1_a_m1_d2", "st_l1_a_m1_d3",
                "st_l1_l_m1_d1", "st_l1_l_m1_d2", "st_l1_l_m1_d3",
                "rv1_m1_ac", "rv1_m1_bd",
            ],
            "est_l1_m2": [
                "st_l1_a_m2_d1", "st_l1_a_m2_d2", "st_l1_a_m2_d3",
                "st_l1_l_m2_d1", "st_l1_l_m2_d2", "st_l1_l_m2_d3",
                "rv1_m2_ac", "rv1_m2_bd",
            ],
            "est_l3_m1": [
                "st_l3_a_m1_d1", "st_l3_a_m1_d2", "st_l3_a_m1_d3",
                "st_l3_l_m1_d1", "st_l3_l_m1_d2", "st_l3_l_m1_d3",
                "rv3_m1_ac", "rv3_m1_bd",
            ],
            "est_l3_m2": [
                "st_l3_a_m2_d1", "st_l3_a_m2_d2", "st_l3_a_m2_d3",
                "st_l3_l_m2_d1", "st_l3_l_m2_d2", "st_l3_l_m2_d3",
                "rv3_m2_ac", "rv3_m2_bd",
            ],
            "est_l5_m1": [
                "st_l5_a_m1_d1", "st_l5_a_m1_d2", "st_l5_a_m1_d3",
                "st_l5_l_m1_d1", "st_l5_l_m1_d2", "st_l5_l_m1_d3",
                "rv5_m1_ac", "rv5_m1_bd",
            ],
            "est_l5_m2": [
                "st_l5_a_m2_d1", "st_l5_a_m2_d2", "st_l5_a_m2_d3",
                "st_l5_l_m2_d1", "st_l5_l_m2_d2", "st_l5_l_m2_d3",
                "rv5_m2_ac", "rv5_m2_bd",
            ],
            "est_ln_m1": [
                "rvn_n",
                "st_ln_a_m1_d1", "st_ln_a_m1_d2", "st_ln_a_m1_d3",
                "st_ln_l_m1_d1", "st_ln_l_m1_d2", "st_ln_l_m1_d3",
                "rvn_m1_ac", "rvn_m1_bd",
            ],
            "est_ln_m2": [
                "st_ln_a_m2_d1", "st_ln_a_m2_d2", "st_ln_a_m2_d3",
                "st_ln_l_m2_d1", "st_ln_l_m2_d2", "st_ln_l_m2_d3",
                "rvn_m2_ac", "rvn_m2_bd",
            ],
            "densidad": ["den_1", "den_2", "den_3"],
            "ancho": ["anc_1", "anc_2", "anc_3"],
            "inclinacion": ["tilt_before_m1", "tilt_before_m2", "tilt_before_dir_m1", "tilt_before_dir_m2"],
            "inclinacion_after": ["tilt_after_m1", "tilt_after_m2", "tilt_after_dir_m1", "tilt_after_dir_m2"],
        }
        return map_steps.get(step_key, [])

    def _is_tilt_required(self):
        self.ensure_one()
        # La inclinacion antes de lavar se captura SIEMPRE en el 1er lavado,
        # aunque el producto no tenga estandar (o no tenga producto). El
        # criterio pass/fail solo se aplica cuando existe estandar
        # (ver _compute_result_state).
        return bool(int(self.wash_number or 0) == 1)

    @staticmethod
    def _raw_has_value(raw):
        return str(raw if raw is not None else "").strip() != ""

    def _validate_tilt_required_values(self, values):
        self.ensure_one()
        if not self._is_tilt_required():
            return
        if not self._raw_has_value((values or {}).get("tilt_before_m1")):
            raise UserError(_("Debe registrar la inclinacion antes de lavar de la muestra 1."))
        if not self._raw_has_value((values or {}).get("tilt_before_m2")):
            raise UserError(_("Debe registrar la inclinacion antes de lavar de la muestra 2."))

    def _check_stability_sequence(self, step_key):
        self.ensure_one()
        if step_key == "est_l1_m1":
            return
        if step_key == "est_l1_m2" and not self.est_l1_ancho_done:
            raise UserError(_("Primero debe registrar la Muestra 1 del 1er lavado para esta partida."))
        if step_key == "est_l3_m1" and not self.est_l1_done:
            raise UserError(_("Primero debe completar el 1er lavado para esta partida."))
        if step_key == "est_l3_m2" and not self.est_l3_ancho_done:
            raise UserError(_("Primero debe registrar la Muestra 1 del 3er lavado para esta partida."))
        if step_key == "est_l5_m1" and not self.est_l3_done:
            raise UserError(_("Primero debe completar el 3er lavado para esta partida."))
        if step_key == "est_l5_m2" and not self.est_l5_ancho_done:
            raise UserError(_("Primero debe registrar la Muestra 1 del 5to lavado para esta partida."))
        if step_key == "est_ln_m2" and int(self.wash_number or 0) < 2:
            raise UserError(_("Primero debe registrar la Muestra 1 del revirado N (incluye Lavado N)."))

    def _to_tablet_payload(self):
        self.ensure_one()
        return {
            "id": self.id,
            "name": self.name,
            "batch_id": self.batch_id.id,
            "wash_number": int(self.wash_number or 0),
            "repeat_kind": self.repeat_kind or "original",
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

    def _append_stage_user(self, user=None):
        self.ensure_one()
        user = user or self.env.user
        if not user:
            return
        existing_ids = list(self.user_ids.ids)
        if user.id in existing_ids:
            return
        self.write({"user_ids": [(6, 0, existing_ids + [user.id])]})
        laboratorio_records = self.env["qc.lab.record"].search([
            ("est_revirado_eval_id", "=", self.id),
        ])
        if laboratorio_records:
            laboratorio_records._sync_involved_users()

    def _has_measure_value(self, key):
        self.ensure_one()
        for lookup_key in self._lookup_keys_for_query(key, self.wash_number):
            if self.detail_line_ids.filtered(lambda l: l.measure_key == lookup_key)[:1]:
                return True
        return False

    def _step_is_complete(self, step_key):
        self.ensure_one()
        for field_name in self._step_fields(step_key):
            if field_name == "rvn_n":
                if int(self.wash_number or 0) < 2:
                    return False
                continue
            if field_name.startswith("tilt_before") and not self._is_tilt_required():
                continue
            if not self._has_measure_value(field_name):
                return False
        return True

    def _mode_is_complete(self, eval_mode):
        self.ensure_one()
        for field_name in self._fields_for_mode(eval_mode):
            if field_name == "rvn_n":
                if int(self.wash_number or 0) < 2:
                    return False
                continue
            if field_name.startswith("tilt_before") and not self._is_tilt_required():
                continue
            if not self._has_measure_value(field_name):
                return False
        return True

    def _refresh_mode_done_flags(self):
        self.ensure_one()
        self.write({
            "est_l1_ancho_done": self._step_is_complete("est_l1_m1"),
            "est_l1_largo_done": self._step_is_complete("est_l1_m2"),
            "est_l1_done": self._mode_is_complete("l1"),
            "est_l3_ancho_done": self._step_is_complete("est_l3_m1"),
            "est_l3_largo_done": self._step_is_complete("est_l3_m2"),
            "est_l3_done": self._mode_is_complete("l3"),
            "est_l5_ancho_done": self._step_is_complete("est_l5_m1"),
            "est_l5_largo_done": self._step_is_complete("est_l5_m2"),
            "est_l5_done": self._mode_is_complete("l5"),
        })

    @api.model
    def _fields_for_mode(self, eval_mode):
        step_keys = self._MODE_STEP_KEYS.get(eval_mode, ())
        if eval_mode == "l1":
            step_keys = tuple(step_keys) + ("inclinacion", "inclinacion_after")
        else:
            step_keys = tuple(step_keys) + ("inclinacion_after",)
        fields = []
        for key in step_keys:
            fields.extend(self._step_fields(key))
        # Preserve order and uniqueness.
        return list(dict.fromkeys(fields))

    @api.model
    def _tablet_recent_density_width(self, pedido_line, limit=10):
        pedido_line = pedido_line.sudo()
        if not pedido_line:
            return []

        # Partidas del mismo artículo y color: sus últimas densidades/anchos
        # sirven de referencia al evaluar esta partida.
        if not pedido_line.qc_product_id:
            return []
        line_domain = [
            ("state", "in", ("batch", "split")),
            ("qc_product_id", "=", pedido_line.qc_product_id.id),
        ]
        if pedido_line.lab_dev_line_id:
            line_domain.append(("lab_dev_line_id", "=", pedido_line.lab_dev_line_id.id))

        if pedido_line.color_code:
            line_domain.append(("color_code", "=", pedido_line.color_code))
        elif pedido_line.color_name:
            line_domain.append(("color_name", "=", pedido_line.color_name))

        same_lines = self.env["mrp.workorder.batch"].sudo().search(line_domain)
        if not same_lines:
            return []

        # Sub-partidas hermanas (misma partida de teñido) comparten referencia.
        candidate_line_ids = set(same_lines.ids)
        parents = same_lines.parent_batch_id | same_lines
        candidate_line_ids.update(parents.ids)
        candidate_line_ids.update(parents.child_batch_ids.ids)

        evals = self.sudo().search([
            ("batch_id", "in", list(candidate_line_ids)),
        ], order="fecha_eval desc, id desc", limit=max(int(limit or 10), 1))

        rows = []
        for rec in evals:
            densidad_1 = float(rec._get_measure_value("den_1") or 0.0)
            densidad_2 = float(rec._get_measure_value("den_2") or 0.0)
            densidad_3 = float(rec._get_measure_value("den_3") or 0.0)
            ancho_1 = float(rec._get_measure_value("anc_1") or 0.0)
            ancho_2 = float(rec._get_measure_value("anc_2") or 0.0)
            ancho_3 = float(rec._get_measure_value("anc_3") or 0.0)
            densidad_promedio = float(rec.densidad_promedio or 0.0)
            ancho_promedio = float(rec.ancho_promedio or 0.0)

            # Keep only rows that have at least one positive measurement.
            if max(
                densidad_1,
                densidad_2,
                densidad_3,
                ancho_1,
                ancho_2,
                ancho_3,
                densidad_promedio,
                ancho_promedio,
            ) <= 0.0:
                continue

            rows.append({
                "eval_id": rec.id,
                "fecha_eval": fields.Datetime.to_string(rec.fecha_eval) if rec.fecha_eval else "",
                "batch": rec.batch_id.name or "",
                "wash_number": int(rec.wash_number or 0),
                "densidad_1": densidad_1,
                "densidad_2": densidad_2,
                "densidad_3": densidad_3,
                "ancho_1": ancho_1,
                "ancho_2": ancho_2,
                "ancho_3": ancho_3,
                "densidad_promedio": densidad_promedio,
                "ancho_promedio": ancho_promedio,
            })
        return rows

    @api.model
    def _tablet_evaluation_standards(self, pedido_line):
        pedido_line = pedido_line.sudo()
        analysis = pedido_line.qc_product_id.analysis_id if pedido_line and pedido_line.qc_product_id else False
        thresholds = analysis.density_stability_twisting_id if analysis else False

        def _as_float(value):
            return float(value or 0.0)

        def _as_percentage(value):
            numeric = abs(_as_float(value))
            return numeric * 100 if numeric <= 1.0 else numeric

        return {
            "density_standard": _as_float(analysis.density) if analysis else 0.0,
            "width_standard": _as_float(analysis.standard_width) if analysis else 0.0,
            "tilt_standard": _as_float(analysis.tilt) if analysis else 0.0,
            "width_shrinkage_from": _as_float(thresholds.width_shrinkage_from) * 100 if thresholds else 0.0,
            "width_shrinkage_to": _as_float(thresholds.width_shrinkage_to) * 100 if thresholds else 0.0,
            "length_shrinkage_from": _as_float(thresholds.length_shrinkage_from) * 100 if thresholds else 0.0,
            "length_shrinkage_to": _as_float(thresholds.length_shrinkage_to) * 100 if thresholds else 0.0,
            "twist_limit": _as_percentage(thresholds.twist) if thresholds else 0.0,
            "tilt_wash_tolerance": _as_float(thresholds.tilt_wash) if thresholds else 0.0,
            "density_tolerance": _as_percentage(thresholds.density) if thresholds else 0.0,
            "width_tolerance": _as_float(thresholds.width) if thresholds else 0.0,
            "has_thresholds": bool(thresholds),
        }

    @api.model
    def action_tablet_get_eval_context(self, batch_id, sample_type=False):
        pedido_line = self.env["mrp.workorder.batch"].browse(int(batch_id or 0))
        if not pedido_line.exists():
            raise UserError(_("Seleccione una partida valida."))

        sample_type = sample_type or "acabado"
        valid_sample_types = {key for key, _label in self._SAMPLE_TYPE_SELECTION}
        if sample_type not in valid_sample_types:
            raise UserError(_("Tipo de muestra invalido."))

        # Los tests son no oficiales: no cuentan para el estado del 1er lavado.
        official = [("repeat_kind", "!=", "test")]
        first_eval_incomplete = self.search([
            ("batch_id", "=", pedido_line.id),
            ("wash_number", "=", 1),
            ("sample_type", "=", sample_type),
            ("est_l1_done", "=", False),
        ] + official, order="fecha_eval desc, id desc", limit=1)
        first_eval_done_latest = self.search([
            ("batch_id", "=", pedido_line.id),
            ("wash_number", "=", 1),
            ("sample_type", "=", sample_type),
            ("est_l1_done", "=", True),
        ] + official, order="fecha_eval desc, id desc", limit=1)
        first_eval_pass_latest = self.search([
            ("batch_id", "=", pedido_line.id),
            ("wash_number", "=", 1),
            ("sample_type", "=", sample_type),
            ("est_l1_done", "=", True),
            ("state", "=", "pass"),
        ] + official, order="fecha_eval desc, id desc", limit=1)

        has_first_record = bool(first_eval_pass_latest)
        requires_first_wash_decision = bool(first_eval_done_latest and not first_eval_pass_latest and not first_eval_incomplete)
        required_mode = "l1" if first_eval_incomplete else (False if has_first_record else (False if requires_first_wash_decision else "l1"))
        available_modes = ["l3", "l5", "ln"] if (has_first_record or requires_first_wash_decision) else ["l1"]

        analysis = pedido_line.qc_product_id.analysis_id
        tilt_standard = float(analysis.tilt or 0.0) if analysis else 0.0
        standards = self._tablet_evaluation_standards(pedido_line)
        # Datos del ultimo 1er lavado oficial, para el modo Editar en sitio.
        editable_first = first_eval_incomplete or first_eval_done_latest

        # Lavados que YA tienen una evaluacion oficial completa: al re-seleccionar
        # ese lavado, la pantalla ofrece Editar / Reproceso / Test.
        completed_wash_numbers = []
        official_recs = self.search([
            ("batch_id", "=", pedido_line.id),
            ("sample_type", "=", sample_type),
        ] + official)
        for rec in official_recs:
            wn = int(rec.wash_number or 0)
            if rec._mode_is_complete(self._wash_code_from_number(wn)):
                completed_wash_numbers.append(wn)
        completed_wash_numbers = sorted(set(completed_wash_numbers))
        return {
            "sample_type": sample_type,
            "has_first_record": has_first_record,
            "required_mode": required_mode,
            "available_modes": available_modes,
            "requires_first_wash_decision": requires_first_wash_decision,
            "first_wash_status": (first_eval_done_latest.state if first_eval_done_latest else "nodata"),
            # La inclinacion antes de lavar se pide SIEMPRE en 1er lavado.
            "tilt_required": bool(required_mode == "l1"),
            "tilt_standard": tilt_standard,
            "standards": standards,
            "recent_density_width": self._tablet_recent_density_width(pedido_line, limit=10),
            "existing_eval": first_eval_incomplete._to_tablet_payload() if first_eval_incomplete else False,
            "editable_first_eval": editable_first._to_tablet_payload() if editable_first else False,
            "completed_wash_numbers": completed_wash_numbers,
        }

    @api.model
    def action_tablet_get_wash_payload(self, batch_id, wash_number, sample_type=False):
        """Ultimo registro OFICIAL de un lavado dado (para el modo Editar de
        lavados posteriores al primero)."""
        pedido_line = self.env["mrp.workorder.batch"].browse(int(batch_id or 0))
        if not pedido_line.exists():
            raise UserError(_("Seleccione una partida valida."))
        sample_type = sample_type or "acabado"
        rec = self.search([
            ("batch_id", "=", pedido_line.id),
            ("sample_type", "=", sample_type),
            ("wash_number", "=", int(wash_number or 0)),
            ("repeat_kind", "!=", "test"),
        ], order="fecha_eval desc, id desc", limit=1)
        return rec._to_tablet_payload() if rec else False

    @api.model
    def action_tablet_finalize(self, batch_id, eval_mode, values, sample_type=False, criteria_override=False, is_progress=False, repeat_mode=""):
        pedido_line = self.env["mrp.workorder.batch"].browse(int(batch_id or 0))
        if not pedido_line.exists():
            raise UserError(_("Seleccione una partida valida."))

        sample_type = sample_type or "acabado"
        valid_sample_types = {key for key, _label in self._SAMPLE_TYPE_SELECTION}
        if sample_type not in valid_sample_types:
            raise UserError(_("Tipo de muestra invalido."))

        eval_mode = (eval_mode or "").strip()
        if eval_mode not in self._MODE_STEP_KEYS:
            raise UserError(_("Modo de evaluacion invalido."))

        repeat_mode = (repeat_mode or "").strip()
        if repeat_mode not in ("", "reproceso", "test", "editar"):
            raise UserError(_("Modo de repeticion invalido."))

        # Los tests son no oficiales: no cuentan para el estado del 1er lavado.
        official = [("repeat_kind", "!=", "test")]
        first_eval_pass_latest = self.search([
            ("batch_id", "=", pedido_line.id),
            ("wash_number", "=", 1),
            ("sample_type", "=", sample_type),
            ("est_l1_done", "=", True),
            ("state", "=", "pass"),
        ] + official, order="fecha_eval desc, id desc", limit=1)
        first_eval_done_latest = self.search([
            ("batch_id", "=", pedido_line.id),
            ("wash_number", "=", 1),
            ("sample_type", "=", sample_type),
            ("est_l1_done", "=", True),
        ] + official, order="fecha_eval desc, id desc", limit=1)

        if eval_mode != "l1" and not first_eval_pass_latest:
            if not criteria_override:
                raise UserError(_("El primer lavado esta en fail. Debe repetir 1er lavado o continuar bajo criterio."))
            if not first_eval_done_latest:
                raise UserError(_("La primera evaluacion de la partida debe ser 1er lavado con ancho y densidad."))
            first_eval_done_latest.write({"criteria_force_pass": True})

        fields_for_mode = self._fields_for_mode(eval_mode)
        if not fields_for_mode:
            raise UserError(_("No hay campos configurados para el modo seleccionado."))

        wash_number = self._WASH_NUMBER_BY_MODE.get(eval_mode)
        if eval_mode == "ln":
            try:
                wash_number = int(float((values or {}).get("rvn_n") or 0.0))
            except (TypeError, ValueError):
                raise UserError(_("El valor de rvn_n no es numerico."))

        if int(wash_number or 0) < 1:
            raise UserError(_("Debe indicar un numero de lavado valido."))

        base_domain = [
            ("batch_id", "=", pedido_line.id),
            ("wash_number", "=", int(wash_number)),
            ("sample_type", "=", sample_type),
        ]
        if repeat_mode == "editar":
            # Editar en sitio: reutiliza el ultimo registro OFICIAL de ese
            # lavado y sobrescribe sus datos (no crea uno nuevo).
            rec = self.search(base_domain + official, order="fecha_eval desc, id desc", limit=1)
        elif repeat_mode in ("reproceso", "test"):
            # Repeticion: siempre crea un registro nuevo.
            rec = self.browse()
        elif eval_mode == "l1":
            rec = self.search(base_domain + [("est_l1_done", "=", False)] + official, order="fecha_eval desc, id desc", limit=1)
        else:
            # Reuse only an in-progress eval; if latest is complete, create a new one.
            rec = self.search(base_domain, order="fecha_eval desc, id desc", limit=1)
            if rec and rec._mode_is_complete(eval_mode):
                rec = self.browse()
        if not rec:
            create_vals = {
                "batch_id": pedido_line.id,
                "wash_number": int(wash_number),
                "sample_type": sample_type,
            }
            if repeat_mode in ("reproceso", "test"):
                create_vals["repeat_kind"] = repeat_mode
            rec = self.create(create_vals)
        rec._append_stage_user(self.env.user)

        if eval_mode == "l1":
            densidad_complete = all(self._raw_has_value((values or {}).get(k)) for k in ("den_1", "den_2", "den_3"))
            ancho_complete = all(self._raw_has_value((values or {}).get(k)) for k in ("anc_1", "anc_2", "anc_3"))
            if not (densidad_complete and ancho_complete):
                raise UserError(_("Para guardar el avance del 1er lavado debe registrar primero ancho y densidad completos."))
            if is_progress and rec._is_tilt_required():
                has_tilt_before = (
                    self._raw_has_value((values or {}).get("tilt_before_m1"))
                    and self._raw_has_value((values or {}).get("tilt_before_m2"))
                ) or (
                    rec._has_measure_value("tilt_before_m1") and rec._has_measure_value("tilt_before_m2")
                )
                if not has_tilt_before:
                    raise UserError(_("Para guardar avance del 1er lavado debe registrar la inclinacion inicial."))

        incoming_values = values or {}
        for value_key, dir_key in (
            ("tilt_before_m1", "tilt_before_dir_m1"),
            ("tilt_before_m2", "tilt_before_dir_m2"),
            ("tilt_after_m1", "tilt_after_dir_m1"),
            ("tilt_after_m2", "tilt_after_dir_m2"),
        ):
            if self._raw_has_value(incoming_values.get(value_key)) and not self._raw_has_value(incoming_values.get(dir_key)):
                incoming_values[dir_key] = "z"
        if (
            rec._raw_has_value(incoming_values.get("tilt_before_m1"))
            or rec._raw_has_value(incoming_values.get("tilt_before_m2"))
        ):
            rec._validate_tilt_required_values(incoming_values)

        if not is_progress and (
            not rec._raw_has_value(incoming_values.get("tilt_after_m1"))
            or not rec._raw_has_value(incoming_values.get("tilt_after_m2"))
        ):
            raise UserError(_("Debe registrar la inclinacion despues de lavar para finalizar."))

        for fname in fields_for_mode:
            if fname == "rvn_n":
                continue
            if fname not in incoming_values:
                continue
            raw = incoming_values.get(fname)
            if not self._raw_has_value(raw):
                continue
            try:
                if fname == "rvn_n":
                    value = int(float(raw or 0.0))
                elif fname.startswith("tilt_") and "_dir_" in fname:
                    raw_dir = str(raw or "").strip().lower()
                    if raw_dir in ("s", "-1"):
                        value = -1.0
                    elif raw_dir in ("z", "1", ""):
                        value = 1.0
                    else:
                        raise UserError(_("El valor de %s no es valido. Use Z o S.") % fname)
                else:
                    value = float(raw or 0.0)
            except (TypeError, ValueError):
                raise UserError(_("El valor de %s no es numerico.") % fname)
            rec._upsert_measure_value(fname, value)

        if eval_mode == "ln" and int(rec.wash_number or 0) < 2:
            raise UserError(_("El lavado N debe ser mayor a 1."))

        rec._refresh_mode_done_flags()
        is_complete = rec._mode_is_complete(eval_mode)
        if eval_mode == "l1" and not is_complete:
            l1_stability_keys = self._step_fields("est_l1_m1") + self._step_fields("est_l1_m2")
            has_started_l1_stability = any(rec._has_measure_value(key) for key in l1_stability_keys)
            if has_started_l1_stability:
                raise UserError(_("Para terminar la evaluacion del 1er lavado falta completar datos de estabilidad/revirado."))

        laboratorio_records = self.env["qc.lab.record"].search([("est_revirado_eval_id", "=", rec.id)])
        if laboratorio_records:
            laboratorio_records._sync_result_lines()

        return {"ok": True, "id": rec.id, "name": rec.name, "completed": bool(is_complete), "repeat_kind": rec.repeat_kind or "original"}

    @api.model
    def action_tablet_get_or_create(self, batch_id, sample_type=False):
        pedido_line = self.env["mrp.workorder.batch"].browse(int(batch_id or 0))
        if not pedido_line.exists():
            raise UserError(_("Seleccione una partida valida."))

        sample_type = sample_type or "acabado"
        valid_sample_types = {key for key, _label in self._SAMPLE_TYPE_SELECTION}
        if sample_type not in valid_sample_types:
            raise UserError(_("Tipo de muestra invalido."))

        rec = self.search([
            ("batch_id", "=", pedido_line.id),
            ("sample_type", "=", sample_type),
        ], limit=1)
        if not rec:
            rec = self.create({
                "batch_id": pedido_line.id,
                "sample_type": sample_type,
            })
        rec._append_stage_user(self.env.user)
        return rec._to_tablet_payload()

    @api.model
    def action_tablet_get_partidas(self, query="", limit=50):
        query = (query or "").strip()
        domain = Domain("state", "=", "batch")
        if query:
            terms = [term.strip() for term in query.split(",") if term.strip()] or [query]
            domain &= Domain.AND([
                Domain.OR([
                    Domain("name", "ilike", term),
                    Domain("qc_customer", "ilike", term),
                    Domain("qc_article", "ilike", term),
                    Domain("color_name", "ilike", term),
                    Domain("color_code", "ilike", term),
                ])
                for term in terms
            ])

        safe_limit = min(max(int(limit or 50), 1), 300)
        lines = self.env["mrp.workorder.batch"].search(domain, order="name desc, id desc", limit=safe_limit)
        return [{
            "id": line.id,
            "label": f"{line.name or '-'} | {line.qc_customer or '-'}",
            "batch": line.name or "",
            "customer": line.qc_customer or "",
            "article": line.qc_article or "",
            "color_name": line.color_name or "",
            "color_code": line.color_code or "",
            "kilograms": float(line.kilograms or 0.0),
            "oc_cliente": line.qc_client_order_ref or "",
            "observaciones": line.qc_order_note or "",
        } for line in lines]

    def action_print_report(self):
        self.ensure_one()

        laboratorio_model = self.env["qc.lab.record"]
        record = laboratorio_model.search([
            ("est_revirado_eval_id", "=", self.id),
        ], limit=1)

        if not record:
            first_user = self.user_ids[:1] or self.env.user
            record = laboratorio_model.create({
                "batch_id": self.batch_id.id,
                "fecha_eval": self.fecha_eval,
                "user_id": first_user.id,
                "test_type": "dimrev",
                "result_state": "uncomplete",
                "est_revirado_eval_id": self.id,
            })

        return record.action_print_report()

    @api.model
    def action_tablet_submit_step(self, batch_id, step_key, values, sample_type=False):
        pedido_line = self.env["mrp.workorder.batch"].browse(int(batch_id or 0))
        if not pedido_line.exists():
            raise UserError(_("Seleccione una partida valida."))

        sample_type = sample_type or "acabado"
        valid_sample_types = {key for key, _label in self._SAMPLE_TYPE_SELECTION}
        if sample_type not in valid_sample_types:
            raise UserError(_("Tipo de muestra invalido."))

        fields_for_step = self._step_fields((step_key or "").strip())
        if not fields_for_step:
            raise UserError(_("Paso de evaluacion invalido."))

        rec = self.search([
            ("batch_id", "=", pedido_line.id),
            ("sample_type", "=", sample_type),
        ], limit=1)
        if not rec:
            rec = self.create({
                "batch_id": pedido_line.id,
                "sample_type": sample_type,
            })
        rec._append_stage_user(self.env.user)

        wash_mode = ""
        step_parts = (step_key or "").split("_")
        if len(step_parts) >= 2 and step_parts[0] == "est":
            wash_mode = step_parts[1]
        if wash_mode in self._WASH_NUMBER_BY_MODE:
            rec.wash_number = self._WASH_NUMBER_BY_MODE[wash_mode]
        elif step_key in ("est_ln_m1", "est_ln_m2"):
            try:
                rec.wash_number = int(float((values or {}).get("rvn_n") or rec.wash_number or 0.0))
            except (TypeError, ValueError):
                raise UserError(_("El valor de rvn_n no es numerico."))

        rec._check_stability_sequence(step_key)
        if any(name.startswith("tilt_before") or name.startswith("tilt_after") for name in fields_for_step):
            rec._validate_tilt_required_values(values)

        for fname in fields_for_step:
            if fname == "rvn_n":
                continue
            raw = (values or {}).get(fname, 0.0)
            try:
                value = int(float(raw or 0.0)) if fname == "rvn_n" else float(raw or 0.0)
            except (TypeError, ValueError):
                raise UserError(_("El valor de %s no es numerico.") % fname)
            rec._upsert_measure_value(fname, value)

        if step_key in ("est_ln_m1", "est_ln_m2") and int(rec.wash_number or 0) < 2:
            raise UserError(_("El lavado N debe ser mayor o igual a 2."))

        write_vals = {}
        if step_key == "est_l1_m1":
            write_vals["est_l1_ancho_done"] = True
        elif step_key == "est_l1_m2":
            write_vals.update({"est_l1_largo_done": True, "est_l1_done": True})
        elif step_key == "est_l3_m1":
            write_vals["est_l3_ancho_done"] = True
        elif step_key == "est_l3_m2":
            write_vals.update({"est_l3_largo_done": True, "est_l3_done": True})
        elif step_key == "est_l5_m1":
            write_vals["est_l5_ancho_done"] = True
        elif step_key == "est_l5_m2":
            write_vals.update({"est_l5_largo_done": True, "est_l5_done": True})

        if write_vals:
            rec.write(write_vals)

        rec._refresh_mode_done_flags()

        laboratorio_records = self.env["qc.lab.record"].search([("est_revirado_eval_id", "=", rec.id)])
        if laboratorio_records:
            laboratorio_records._sync_result_lines()

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

    @api.depends(
        "est_ancho_avg",
        "est_largo_avg",
        "revirado_promedio",
        "tilt_before",
        "densidad_promedio",
        "ancho_promedio",
        "criteria_force_pass",
    )
    def _compute_result_state(self):
        for rec in self:
            result = "pass"
            bool_fields = (
                "bool_est_ancho_avg",
                "bool_est_largo_avg",
                "bool_revirado_promedio",
                "bool_tilt_before",
                "bool_densidad_promedio",
                "bool_ancho_promedio",
            )
            for field_name in bool_fields:
                rec[field_name] = True

            if rec.criteria_force_pass:
                rec.state = "pass"
                continue

            analysis = rec.batch_id.qc_product_id.analysis_id
            thresholds = analysis.density_stability_twisting_id if analysis else False
            std_density = float(analysis.density or 0.0) if analysis else 0.0
            std_width = float(analysis.standard_width or 0.0) if analysis else 0.0
            tilt_standard = float(analysis.tilt or 0.0) if analysis else 0.0

            has_complete_est_ancho = all(rec._has_measure_value(key) for key in (
                "st_a_m1_d1", "st_a_m1_d2", "st_a_m1_d3",
                "st_a_m2_d1", "st_a_m2_d2", "st_a_m2_d3",
            ))
            has_complete_est_largo = all(rec._has_measure_value(key) for key in (
                "st_l_m1_d1", "st_l_m1_d2", "st_l_m1_d3",
                "st_l_m2_d1", "st_l_m2_d2", "st_l_m2_d3",
            ))
            has_complete_revirado = all(rec._has_measure_value(key) for key in (
                "rv_m1_ac", "rv_m1_bd", "rv_m2_ac", "rv_m2_bd",
            ))
            has_complete_tilt_before = rec._has_measure_value("tilt_before_m1") and rec._has_measure_value("tilt_before_m2")
            has_complete_densidad = all(rec._has_measure_value(key) for key in ("den_1", "den_2", "den_3"))
            has_complete_ancho = all(rec._has_measure_value(key) for key in ("anc_1", "anc_2", "anc_3"))

            def _tol_ratio(raw_value):
                value = abs(float(raw_value or 0.0))
                # Accept both styles: 0.02 (2%) or 2 (2%).
                return value / 100.0 if value > 1.0 else value

            def _tol_abs(raw_value):
                return abs(float(raw_value or 0.0))

            def _tol_percent(raw_value):
                value = abs(float(raw_value or 0.0))
                return value * 100.0 if value <= 1.0 else value

            if not thresholds:
                result = "nodata"
            else:
                width_from = thresholds.width_shrinkage_from * 100
                width_to = thresholds.width_shrinkage_to * 100
                length_from = thresholds.length_shrinkage_from * 100
                length_to = thresholds.length_shrinkage_to * 100
                density_tol = _tol_ratio(thresholds.density)
                width_tol_cm = _tol_abs(thresholds.width)

                # Densidad y ancho solo se validan en 1er lavado.
                if int(rec.wash_number or 0) == 1:
                    if std_density > 0 and has_complete_densidad:
                        density_min = std_density * (1.0 - density_tol)
                        density_max = std_density * (1.0 + density_tol)
                        if not (density_min <= rec.densidad_promedio <= density_max):
                            rec.bool_densidad_promedio = False

                    if std_width > 0 and has_complete_ancho:
                        width_min = std_width - width_tol_cm
                        width_max = std_width + width_tol_cm
                        if not (width_min <= rec.ancho_promedio <= width_max):
                            rec.bool_ancho_promedio = False

                if has_complete_est_ancho and width_from and rec.est_ancho_avg < width_from:
                    rec.bool_est_ancho_avg = False
                if has_complete_est_ancho and width_to and rec.est_ancho_avg > width_to:
                    rec.bool_est_ancho_avg = False

                if has_complete_est_largo and length_from and rec.est_largo_avg < length_from:
                    rec.bool_est_largo_avg = False
                if has_complete_est_largo and length_to and rec.est_largo_avg > length_to:
                    rec.bool_est_largo_avg = False

                twist_limit = _tol_percent(thresholds.twist)
                if has_complete_revirado and twist_limit and rec.revirado_promedio > twist_limit:
                    rec.bool_revirado_promedio = False

                tilt_tolerance = abs(float(thresholds.tilt_wash or 0.0))
                # Inclinacion solo se valida en 1er lavado cuando existe estandar en analysis.
                # Criterio: estandar +/- tolerancia.
                if (
                    int(rec.wash_number or 0) == 1
                    and has_complete_tilt_before
                    and tilt_standard > 0.0
                    and abs(float(rec.tilt_before or 0.0) - tilt_standard) > tilt_tolerance
                ):
                    rec.bool_tilt_before = False

            if any(not rec[field_name] for field_name in bool_fields):
                result = "fail"
            rec.state = result

class ControlEstabilidadReviradoEvalDetail(models.Model):
    _name = "qc.dimstab.eval.detail"
    _description = "Detalle de Evaluacion Estabilidad/Revirado"
    _order = "sequence asc, id asc"

    eval_id = fields.Many2one("qc.dimstab.eval", string="Evaluacion", required=True, ondelete="cascade", index=True)
    sequence = fields.Integer(string="Secuencia", default=10, index=True)
    measure_key = fields.Char(string="Clave", required=True, index=True)
    muestra = fields.Selection([("m1", "M1"), ("m2", "M2"), ("na", "N/A")], string="Muestra", default="na", required=True, index=True)
    evaluacion = fields.Char(string="Item Evaluacion", required=True)
    dato = fields.Float(string="Dato", digits=(16, 1), required=True)
    user_id = fields.Many2one("res.users", string="Usuario", default=lambda self: self.env.user, index=True)
    fecha_registro = fields.Datetime(string="Fecha Registro", default=fields.Datetime.now, index=True)

    _uniq_eval_measure_key = models.Constraint(
        "UNIQUE(eval_id, measure_key)",
        "La clave de medicion ya existe en esta evaluacion.",
    )
