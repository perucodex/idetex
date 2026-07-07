from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ThreadBag(models.Model):
    """Una bolsa física de hilo.

    Es la unidad atómica del control de hilo: cada bolsa tiene un código único
    (Correl), su lote, su cantidad de conos y su PESO NETO propio (cada bolsa
    pesa distinto). El stock de hilo se deriva de las bolsas disponibles, no de
    un cálculo de pesos homogéneos.

        kg de un lote = suma de net_weight de sus bolsas disponibles
        bolsas        = conteo de bolsas disponibles
        conos         = suma de cone_qty de sus bolsas disponibles
    """

    _name = "thread.bag"
    _description = "Bolsa de Hilo"
    _order = "product_id, lot_id, name"
    _rec_name = "name"

    name = fields.Char(
        string="Correlativo", required=True, index=True, copy=False,
        help="Código único de la bolsa (Correl).",
    )
    product_id = fields.Many2one(
        "product.product", string="Artículo", required=True, index=True,
        domain="[('is_thread', '=', True)]", ondelete="restrict",
    )
    lot_id = fields.Many2one(
        "stock.lot", string="Lote", required=True, index=True, ondelete="restrict",
    )
    location_id = fields.Many2one(
        "stock.location", string="Ubicación", index=True,
        domain="[('usage', '=', 'internal')]",
        help="Ubicación física actual de la bolsa.",
    )

    cone_qty = fields.Integer(string="Conos", required=True, default=0)
    gross_weight = fields.Float(string="Peso Bruto (kg)", digits=(16, 3))
    tare = fields.Float(string="Tara (kg)", digits=(16, 3))
    net_weight = fields.Float(
        string="Peso Neto (kg)", required=True, digits=(16, 3),
        help="Peso neto real de esta bolsa (lo que se controla).",
    )
    avg_cone_weight = fields.Float(
        string="Peso x Cono (kg)", compute="_compute_avg_cone_weight", store=True,
        digits=(16, 4), help="Solo informativo = neto / conos.",
    )

    packaging_type = fields.Char(string="Tipo de Empaque", help="CARTÓN / PLÁSTICOS.")
    cone_color = fields.Char(string="Color de Cono")
    yarn_color = fields.Char(string="Color de Hilo")

    state = fields.Selection(
        [
            ("available", "Disponible"),
            ("reserved", "Reservada"),
            ("consumed", "Consumida"),
        ],
        string="Estado", default="available", required=True, index=True, copy=False,
    )

    company_id = fields.Many2one(
        "res.company", string="Compañía", required=True, index=True,
        default=lambda self: self.env.company,
    )

    # Trazabilidad de consumo
    consumed_move_line_id = fields.Many2one(
        "stock.move.line", string="Línea de Movimiento", copy=False, index=True,
        ondelete="set null",
    )
    production_id = fields.Many2one(
        "mrp.production", string="Orden de Fabricación", copy=False, index=True,
    )
    consumed_date = fields.Datetime(string="Fecha de Consumo", copy=False)

    receipt_picking_id = fields.Many2one(
        "stock.picking", string="Recepción", copy=False, index=True,
        ondelete="set null", help="Recepción que dio de alta esta bolsa.",
    )

    _name_company_uniq = models.Constraint(
        "unique(name, company_id)",
        "Ya existe una bolsa con ese correlativo en esta compañía.",
    )

    @api.depends("net_weight", "cone_qty")
    def _compute_avg_cone_weight(self):
        for bag in self:
            bag.avg_cone_weight = (bag.net_weight / bag.cone_qty) if bag.cone_qty else 0.0

    @api.depends("name", "net_weight", "cone_qty", "lot_id")
    def _compute_display_name(self):
        for bag in self:
            bag.display_name = "%s · %s · %d conos · %.3f kg" % (
                bag.name or "?", bag.lot_id.name or "?",
                bag.cone_qty or 0, bag.net_weight or 0.0,
            )

    @api.constrains("net_weight", "cone_qty")
    def _check_positive(self):
        for bag in self:
            if bag.net_weight <= 0:
                raise ValidationError(_("El peso neto de la bolsa debe ser mayor a 0."))
            if bag.cone_qty <= 0:
                raise ValidationError(_("Los conos de la bolsa deben ser mayor a 0."))

    @api.constrains("lot_id", "product_id")
    def _check_lot_product(self):
        for bag in self:
            if bag.lot_id and bag.product_id and bag.lot_id.product_id != bag.product_id:
                raise ValidationError(_(
                    "El lote %(lot)s no corresponde al artículo %(prod)s.",
                    lot=bag.lot_id.name, prod=bag.product_id.display_name,
                ))

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @api.model
    def _get_or_create_lot(self, product, lot_name, company):
        """Devuelve (creando si hace falta) el stock.lot de (producto, lote)."""
        lot_name = (lot_name or "").strip()
        Lot = self.env["stock.lot"]
        lot = Lot.search([
            ("name", "=", lot_name),
            ("product_id", "=", product.id),
            "|", ("company_id", "=", company.id), ("company_id", "=", False),
        ], limit=1)
        if not lot:
            lot = Lot.create({
                "name": lot_name,
                "product_id": product.id,
                "company_id": company.id,
            })
        return lot

    def action_mark_consumed(self, move_line=False, production=False, location=False):
        """Marca las bolsas como consumidas (uso interno al validar movimientos)."""
        vals = {"state": "consumed", "consumed_date": fields.Datetime.now()}
        if move_line:
            vals["consumed_move_line_id"] = move_line.id
        if production:
            vals["production_id"] = production.id
        if location:
            vals["location_id"] = location.id
        self.write(vals)

    def action_reset_available(self):
        """Vuelve las bolsas a disponible (deshace una reserva/selección)."""
        self.write({
            "state": "available",
            "consumed_move_line_id": False,
            "production_id": False,
            "consumed_date": False,
        })


class ProductTemplate(models.Model):
    _inherit = "product.template"

    thread_available_net = fields.Float(
        string="Kg de Hilo Disponibles", compute="_compute_thread_available_net",
        digits=(16, 3),
    )
    thread_bag_count = fields.Integer(
        string="Bolsas Disponibles", compute="_compute_thread_available_net",
    )

    def _compute_thread_available_net(self):
        Bag = self.env["thread.bag"]
        for tmpl in self:
            if not tmpl.is_thread:
                tmpl.thread_available_net = 0.0
                tmpl.thread_bag_count = 0
                continue
            bags = Bag.search([
                ("product_id.product_tmpl_id", "=", tmpl.id),
                ("state", "=", "available"),
            ])
            tmpl.thread_available_net = sum(bags.mapped("net_weight"))
            tmpl.thread_bag_count = len(bags)

    def action_view_thread_bags(self):
        self.ensure_one()
        product_ids = self.product_variant_ids.ids
        return {
            "type": "ir.actions.act_window",
            "name": _("Bolsas de Hilo"),
            "res_model": "thread.bag",
            "view_mode": "list,form",
            "domain": [("product_id", "in", product_ids)],
            "context": {},
        }
