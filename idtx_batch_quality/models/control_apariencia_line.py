from odoo import api, fields, models
from odoo.fields import Domain
from odoo.exceptions import UserError, ValidationError

class ControlAparienciaLine(models.Model):
    _name = "control.apariencia.line"
    _description = "Apariencia por Rollo"
    _order = "create_date, rollo_num asc, id asc"

    pedido_line_id = fields.Many2one(
        "control.pedido.line",
        string="Partida",
        required=True,
        ondelete="cascade",
        index=True,
    )
    evaluacion_id = fields.Many2one(
        "control.apariencia.eval",
        string="Evaluacion",
        ondelete="cascade",
        index=True,
    )
    apariencia_id = fields.Many2one('control.apariencia', string='Apariencia', required=True)
    rollo_num = fields.Integer(string="N° Rollo", required=True, index=True)
    width = fields.Float('Width (meters)', digits=(10, 2), required=True)
    meters = fields.Float('Meters', digits=(10, 2), required=True)
    defecto_line_ids = fields.One2many(
        "control.apariencia.defecto.line",
        "apariencia_id",
        string="Defectos",
    )

    # Cantidad Defectos = cuantos tipos tienen cantidad > 0
    defect_count = fields.Integer(
        string="Cantidad Defectos",
        compute="_compute_defect_count",
        store=True,
        readonly=True,
    )

    @api.constrains("width", "meters")
    def _check_positive_width_and_meters(self):
        for rec in self:
            if rec.width <= 0:
                raise ValidationError(f"El ancho del rollo {rec.rollo_num} debe ser mayor a 0.")
            if rec.meters <= 0:
                raise ValidationError("El metraje debe ser mayor a 0.")

    @api.constrains("evaluacion_id", "pedido_line_id", "apariencia_id")
    def _check_evaluacion_matches_roll(self):
        for rec in self:
            if not rec.evaluacion_id:
                continue
            if rec.evaluacion_id.pedido_line_id != rec.pedido_line_id:
                raise ValidationError("La evaluacion seleccionada no pertenece a la partida indicada.")
            if rec.evaluacion_id.apariencia_id != rec.apariencia_id:
                raise ValidationError("La evaluacion seleccionada no corresponde al control de apariencia indicado.")

    @api.constrains("evaluacion_id", "rollo_num")
    def _check_rollo_unique_per_evaluacion(self):
        for rec in self:
            if not rec.evaluacion_id or rec.rollo_num <= 0:
                continue
            duplicate = self.search_count([
                ("evaluacion_id", "=", rec.evaluacion_id.id),
                ("rollo_num", "=", rec.rollo_num),
                ("id", "!=", rec.id),
            ])
            if duplicate:
                raise ValidationError(
                    f"El rollo {rec.rollo_num} ya fue registrado en la evaluacion {rec.evaluacion_id.display_name}."
                )

    @api.model_create_multi
    def create(self, vals_list):
        eval_model = self.env["control.apariencia.eval"]
        for vals in vals_list:
            evaluacion_id = vals.get("evaluacion_id")
            pedido_line_id = vals.get("pedido_line_id")
            apariencia_id = vals.get("apariencia_id")

            if evaluacion_id:
                evaluacion = eval_model.browse(evaluacion_id)
                if evaluacion.exists() and not pedido_line_id:
                    vals["pedido_line_id"] = evaluacion.pedido_line_id.id

            if not vals.get("evaluacion_id") and pedido_line_id and apariencia_id:
                evaluacion = eval_model.create({
                    "pedido_line_id": pedido_line_id,
                    "apariencia_id": apariencia_id,
                })
                vals["evaluacion_id"] = evaluacion.id

        return super().create(vals_list)

    def _get_rollo_unique_domain(self, rec):
        if rec.evaluacion_id:
            return [
                ("evaluacion_id", "=", rec.evaluacion_id.id),
                ("rollo_num", "=", rec.rollo_num),
                ("id", "!=", rec.id),
            ]
        return [
            ("pedido_line_id", "=", rec.pedido_line_id.id),
            ("rollo_num", "=", rec.rollo_num),
            ("id", "!=", rec.id),
        ]

    def _get_rollo_unique_create_domain(self, pedido_line_id, rollo_num, evaluacion_id=False):
        if evaluacion_id:
            return [
                ("evaluacion_id", "=", evaluacion_id),
                ("rollo_num", "=", rollo_num),
            ]
        return [
            ("pedido_line_id", "=", pedido_line_id),
            ("rollo_num", "=", rollo_num),
        ]

    @api.model
    def action_tablet_check_rollo_available(self, pedido_line_id, rollo_num, evaluacion_id=False):
        pedido_line_id = int(pedido_line_id or 0)
        rollo_num = int(rollo_num or 0)
        evaluacion_id = int(evaluacion_id or 0)

        if not pedido_line_id:
            return {"ok": False, "message": "Seleccione una partida."}
        if rollo_num <= 0:
            return {"ok": False, "message": "El N° Rollo debe ser mayor a 0."}

        if evaluacion_id:
            evaluacion = self.env["control.apariencia.eval"].browse(evaluacion_id)
            if not evaluacion.exists():
                return {"ok": False, "message": "La evaluacion seleccionada no existe."}
            if evaluacion.pedido_line_id.id != pedido_line_id:
                return {"ok": False, "message": "La evaluacion no pertenece a la partida seleccionada."}

            exists = self.search_count([
                ("evaluacion_id", "=", evaluacion_id),
                ("rollo_num", "=", rollo_num),
            ])
            if exists:
                return {
                    "ok": False,
                    "message": f"El rollo {rollo_num} ya fue registrado en esta evaluacion.",
                }

        return {"ok": True}

    @api.depends("defecto_line_ids.cantidad")
    def _compute_defect_count(self):
        for rec in self:
            rec.defect_count = sum(1 for l in rec.defecto_line_ids if (l.cantidad or 0) > 0)

    @api.model
    def action_tablet_get_apariencias(self, query="", limit=20):
        query = (query or "").strip()
        domain = Domain([])
        if query:
            domain = Domain.AND([domain, Domain("name", "ilike", query)])

        safe_limit = min(max(int(limit or 20), 1), 100)
        apariencias = self.env["control.apariencia"].search(domain, order="name asc, id asc", limit=safe_limit)
        return [
            {
                "id": ap.id,
                "name": ap.name or "",
                "label": ap.name or "-",
            }
            for ap in apariencias
        ]

    @api.model
    def action_tablet_get_partidas(self, query="", limit=20):
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

        safe_limit = min(max(int(limit or 20), 1), 100)
        lines = self.env["control.pedido.line"].search(domain, order="batch desc, id desc", limit=safe_limit)
        return [
            {
                "id": line.id,
                "label": f"{line.batch or '-'} | {line.pedido_id.customer or '-'}",
                "batch": line.batch or "",
                "customer": line.pedido_id.customer or "",
                "article": line.description or "",
                "color_name": line.colorname or "",
                "color_code": line.colorcode or "",
                "kilograms": line.kilograms or 0.0,
            }
            for line in lines
        ]

    @api.model
    def action_tablet_get_defectos(self, apariencia_id=None):
        apariencia_id = int(apariencia_id or 0)
        if not apariencia_id:
            return []

        defectos = self.env["control.apariencia.defecto"].search(
            [("is_active", "=", True), ("apariencia_id", "=", apariencia_id)],
            order="sequence asc, name asc, id asc",
        )
        return [
            {
                "defecto_id": defecto.id,
                "name": defecto.name,
                "is_hueco": bool(defecto.is_hueco),
            }
            for defecto in defectos
        ]

    @api.model
    def action_tablet_finalize(
        self,
        pedido_line_id,
        rollo_num,
        selections,
        width=None,
        meters=None,
        apariencia_id=None,
        evaluacion_id=None,
    ):
        pedido_line = self.env["control.pedido.line"].browse(int(pedido_line_id))
        if not pedido_line.exists():
            raise UserError("La partida seleccionada no existe.")

        apariencia_id = int(apariencia_id or 0)
        apariencia = self.env["control.apariencia"].browse(apariencia_id)
        if not apariencia.exists():
            raise UserError("Seleccione un control de apariencia válido.")

        evaluacion = self.env["control.apariencia.eval"].browse(int(evaluacion_id or 0))
        if evaluacion and not evaluacion.exists():
            raise UserError("La evaluacion seleccionada no existe.")
        if evaluacion and evaluacion.pedido_line_id != pedido_line:
            raise UserError("La evaluacion seleccionada no pertenece a la partida indicada.")
        if evaluacion and evaluacion.apariencia_id != apariencia:
            raise UserError("La evaluacion seleccionada no corresponde al control de apariencia indicado.")

        if not evaluacion:
            evaluacion = self.env["control.apariencia.eval"].create({
                "pedido_line_id": pedido_line.id,
                "apariencia_id": apariencia.id,
            })

        rollo_num = int(rollo_num or 0)
        if rollo_num <= 0:
            raise UserError("El N° Rollo debe ser mayor a 0.")

        exists = self.search_count([
            ("evaluacion_id", "=", evaluacion.id),
            ("rollo_num", "=", rollo_num),
        ])
        if exists:
            raise UserError(f"El rollo {rollo_num} ya fue registrado en esta evaluacion.")

        width = float(width or 0.0)
        if width <= 0:
            raise UserError("El ancho del rollo debe ser mayor a 0.")

        meters = float(meters or 0.0)
        if meters <= 0:
            raise UserError("El metraje debe ser mayor a 0.")

        apariencia_line = self.create(
            self._get_tablet_apariencia_create_vals(
                pedido_line,
                apariencia,
                rollo_num,
                width,
                meters,
                evaluacion,
            )
        )

        defect_cmds = []
        for item in selections or []:
            defecto_id = int(item.get("defecto_id") or 0)
            size_codes = item.get("sizes") or []
            if not defecto_id or not size_codes:
                continue

            defecto = self.env["control.apariencia.defecto"].browse(defecto_id)
            if not defecto.exists():
                continue
            if defecto.apariencia_id.id != apariencia.id:
                continue

            size_cmds = []
            for code in size_codes:
                code = str(code)
                if defecto.is_hueco:
                    if code not in ("2", "4"):
                        raise UserError("Tamaño de hueco inválido.")
                    size_cmds.append((0, 0, {"tamano_hueco": code}))
                else:
                    if code not in ("1", "2", "3", "4"):
                        raise UserError("Tamaño de defecto inválido.")
                    size_cmds.append((0, 0, {"tamano": code}))

            if size_cmds:
                defect_cmds.append((0, 0, {
                    "defecto_id": defecto.id,
                    "tamano_defecto_ids": size_cmds,
                }))

        if defect_cmds:
            apariencia_line.write({"defecto_line_ids": defect_cmds})

        return {
            "ok": True,
            "apariencia_line_id": apariencia_line.id,
            "evaluacion_id": evaluacion.id,
        }

    def _get_tablet_apariencia_create_vals(self, pedido_line, apariencia, rollo_num, width, meters, evaluacion):
        return {
            "pedido_line_id": pedido_line.id,
            "evaluacion_id": evaluacion.id,
            "apariencia_id": apariencia.id,
            "rollo_num": rollo_num,
            "width": width,
            "meters": meters,
        }


class ControlAparienciaDefectoLine(models.Model):
    _name = "control.apariencia.defecto.line"
    _description = "Detalle Defecto Apariencia"
    _order = "id asc"

    apariencia_id = fields.Many2one(
        "control.apariencia.line",
        string="Apariencia",
        required=True,
        ondelete="cascade",
        index=True,
    )
    defecto_id = fields.Many2one(
        "control.apariencia.defecto",
        string="Defecto",
        required=True,
        index=True,
    )
    is_hueco = fields.Boolean(related='defecto_id.is_hueco')
    cantidad = fields.Integer(string="Cantidad", compute="_compute_cantidad")
    tamano_defecto_ids = fields.One2many('control.apariencia.tamano.defecto', 'defecto_line_id', string='Tamaños Defecto')

    @api.depends("tamano_defecto_ids")
    def _compute_cantidad(self):
        for rec in self:
            rec.cantidad = rec.tamano_defecto_ids and len(rec.tamano_defecto_ids) or 0

    @api.constrains("defecto_id", "apariencia_id")
    def _check_defecto_matches_apariencia(self):
        for rec in self:
            if rec.defecto_id and rec.apariencia_id and rec.apariencia_id.apariencia_id:
                if rec.defecto_id.apariencia_id != rec.apariencia_id.apariencia_id:
                    raise ValidationError("El defecto seleccionado no corresponde al control de apariencia elegido.")

class ControlAparienciaTamanoDefecto(models.Model):
    _name = "control.apariencia.tamano.defecto"
    _description = "Detalle Tamaño Defecto Apariencia"
    _order = "id asc"

    defecto_line_id = fields.Many2one(
        "control.apariencia.defecto.line",
        string="Defecto Linea",
        required=True,
        ondelete="cascade",
        index=True,
    )
    tamano = fields.Selection([
        ('1', 'Hasta 7.5 cm'),
        ('2', '> 7.5 cm y hasta 15 cm'),
        ('3', '> 15 cm y hasta 23 cm'),
        ('4', '> 23 cm'),
    ], string='Tamaño del Defecto Calidad')
    tamano_hueco = fields.Selection([
        ('2', '<= 3 cm'),
        ('4', '> 3 cm'),
    ], string='Tamaño del Hueco')