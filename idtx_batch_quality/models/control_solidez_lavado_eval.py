from odoo import _, api, fields, models
from odoo.exceptions import UserError


class ControlSolidezLavadoEval(models.Model):
    _name = "control.solidez.lavado.eval"
    _description = "Evaluacion Solidez del Color al Lavado"
    _order = "fecha_eval desc, id desc"

    _TABLET_FIELDS = (
        "cambio_color_grado",
        "mig_acetato",
        "mig_algodon",
        "mig_nylon",
        "mig_poliester",
        "mig_acrilico",
        "mig_lana",
        "frote_seco",
        "frote_humedo",
    )

    name = fields.Char(string="Referencia", required=True, copy=False, default="New", index=True)
    fecha_eval = fields.Datetime(string="Fecha", required=True, default=fields.Datetime.now, index=True)
    user_id = fields.Many2one("res.users", string="Usuario", required=True, default=lambda self: self.env.user)
    pedido_line_id = fields.Many2one("control.pedido.line", string="Partida", required=True, ondelete="cascade", index=True)

    cambio_color_grado = fields.Float(string="Cambio de color grado", digits=(16, 4), required=True)
    mig_acetato = fields.Float(string="Migracion Acetato", digits=(16, 4), required=True)
    mig_algodon = fields.Float(string="Migracion Algodon", digits=(16, 4), required=True)
    mig_nylon = fields.Float(string="Migracion Nylon", digits=(16, 4), required=True)
    mig_poliester = fields.Float(string="Migracion Poliester", digits=(16, 4), required=True)
    mig_acrilico = fields.Float(string="Migracion Acrilico", digits=(16, 4), required=True)
    mig_lana = fields.Float(string="Migracion Lana", digits=(16, 4), required=True)
    frote_seco = fields.Float(string="Frote Seco", digits=(16, 4), required=True)
    frote_humedo = fields.Float(string="Frote Humedo", digits=(16, 4), required=True)

    @api.model_create_multi
    def create(self, vals_list):
        seq = self.env["ir.sequence"]
        for vals in vals_list:
            if vals.get("name", "New") == "New":
                vals["name"] = seq.next_by_code("control.solidez.lavado.eval") or "New"
        records = super().create(vals_list)

        laboratorio_model = self.env["control.laboratorio.record"]
        for rec in records:
            exists = laboratorio_model.search([("solidez_lavado_eval_id", "=", rec.id)], limit=1)
            if exists:
                continue
            laboratorio_model.create({
                "pedido_line_id": rec.pedido_line_id.id,
                "fecha_eval": rec.fecha_eval,
                "user_id": rec.user_id.id,
                "test_type": "solidez_lavado",
                "result_state": "pasa",
                "solidez_lavado_eval_id": rec.id,
            })
        return records

    @api.model
    def action_tablet_get_partidas(self, query="", limit=50):
        return self.env["control.estabilidad.revirado.eval"].action_tablet_get_partidas(query, limit)

    def write(self, vals):
        res = super().write(vals)
        tracked_fields = set(self._TABLET_FIELDS)
        if tracked_fields.intersection(vals.keys()):
            laboratorio_records = self.env["control.laboratorio.record"].search([
                ("solidez_lavado_eval_id", "in", self.ids),
            ])
            if laboratorio_records:
                laboratorio_records._sync_result_lines()
        return res

    @api.model
    def action_tablet_finalize(self, pedido_line_id, values):
        pedido_line = self.env["control.pedido.line"].browse(int(pedido_line_id or 0))
        if not pedido_line.exists():
            raise UserError(_("Seleccione una partida valida."))

        vals = {
            "pedido_line_id": pedido_line.id,
            "user_id": self.env.user.id,
        }
        for field_name in self._TABLET_FIELDS:
            raw = (values or {}).get(field_name, "")
            if raw in (None, ""):
                raise UserError(_("Complete el campo %s.") % field_name)
            try:
                vals[field_name] = float(raw)
            except (TypeError, ValueError):
                raise UserError(_("El valor de %s no es numerico.") % field_name)

        rec = self.create(vals)

        laboratorio_records = self.env["control.laboratorio.record"].search([("solidez_lavado_eval_id", "=", rec.id)])
        if laboratorio_records:
            laboratorio_records._sync_result_lines()

        return {"ok": True, "id": rec.id, "name": rec.name}
