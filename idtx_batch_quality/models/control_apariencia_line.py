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
    rollo_num = fields.Integer(string="N° Rollo", required=True, index=True)

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

    @api.constrains("rollo_num", "pedido_line_id")
    def _check_rollo_num_unique(self):
        for rec in self:
            if rec.pedido_line_id:
                same_rollo = self.search(self._get_rollo_unique_domain(rec))
                if same_rollo:
                    raise ValidationError("Ya existe un registro con el mismo número de rollo en esta partida.")

    def _get_rollo_unique_domain(self, rec):
        return [
            ("pedido_line_id", "=", rec.pedido_line_id.id),
            ("rollo_num", "=", rec.rollo_num),
            ("id", "!=", rec.id),
        ]

    def _get_rollo_unique_create_domain(self, pedido_line_id, rollo_num):
        return [
            ("pedido_line_id", "=", pedido_line_id),
            ("rollo_num", "=", rollo_num),
        ]

    @api.model
    def action_tablet_check_rollo_available(self, pedido_line_id, rollo_num):
        pedido_line_id = int(pedido_line_id or 0)
        rollo_num = int(rollo_num or 0)

        if not pedido_line_id:
            return {"ok": False, "message": "Seleccione una partida."}
        if rollo_num <= 0:
            return {"ok": False, "message": "El N° Rollo debe ser mayor a 0."}

        exists = bool(self.search_count(self._get_rollo_unique_create_domain(pedido_line_id, rollo_num)))
        if exists:
            return {
                "ok": False,
                "message": "Ya existe un registro con el mismo número de rollo en esta partida.",
            }
        return {"ok": True}

    @api.depends("defecto_line_ids.cantidad")
    def _compute_defect_count(self):
        for rec in self:
            rec.defect_count = sum(1 for l in rec.defecto_line_ids if (l.cantidad or 0) > 0)

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
    def action_tablet_get_defectos(self):
        defectos = self.env["control.apariencia.defecto"].search(
            [("is_active", "=", True)], order="name asc, id asc"
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
    def action_tablet_finalize(self, pedido_line_id, rollo_num, selections):
        pedido_line = self.env["control.pedido.line"].browse(int(pedido_line_id))
        if not pedido_line.exists():
            raise UserError("La partida seleccionada no existe.")

        rollo_num = int(rollo_num or 0)
        if rollo_num <= 0:
            raise UserError("El N° Rollo debe ser mayor a 0.")

        apariencia = self.create(self._get_tablet_apariencia_create_vals(pedido_line, rollo_num))

        defect_cmds = []
        for item in selections or []:
            defecto_id = int(item.get("defecto_id") or 0)
            size_codes = item.get("sizes") or []
            if not defecto_id or not size_codes:
                continue

            defecto = self.env["control.apariencia.defecto"].browse(defecto_id)
            if not defecto.exists():
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
            apariencia.write({"defecto_line_ids": defect_cmds})

        return {"ok": True, "apariencia_id": apariencia.id}

    def _get_tablet_apariencia_create_vals(self, pedido_line, rollo_num):
        return {
            "pedido_line_id": pedido_line.id,
            "rollo_num": rollo_num,
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
    ], string='Tamaño del Defecto')
    tamano_hueco = fields.Selection([
        ('2', '<= 3 cm'),
        ('4', '> 3 cm'),
    ], string='Tamaño del Hueco')