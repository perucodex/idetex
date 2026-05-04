from odoo import api, fields, models
from odoo.exceptions import ValidationError


class ThreadLotControl(models.Model):
    _name = "thread.lot.control"
    _description = "Thread Lot Bag Control"
    _order = "date desc, id desc"

    name = fields.Char(string="Reference", required=True, copy=False, default="New")
    date = fields.Date(string="Date", required=True, default=fields.Date.context_today)
    movement_type = fields.Selection(
        [
            ("in", "Entrada"),
            ("out", "Salida"),
            ("balance", "Segunda Calidad"),
            ("manual", "Manual"),
        ],
        string="Tipo Movimiento",
        required=True,
        default="manual",
        readonly=True,
        index=True,
    )
    lot_id = fields.Many2one(
        "stock.lot",
        string="Lot",
        required=True,
        domain="[('product_id.is_thread', '=', True)]",
        index=True,
    )
    product_id = fields.Many2one(
        "product.product",
        string="Product",
        related="lot_id.product_id",
        store=True,
        readonly=True,
    )
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        related="lot_id.company_id",
        store=True,
        readonly=True,
    )
    source_location_id = fields.Many2one(
        "stock.location",
        string="Source Location",
        readonly=True,
        index=True,
    )
    dest_location_id = fields.Many2one(
        "stock.location",
        string="Destination Location",
        readonly=True,
        index=True,
    )
    line_ids = fields.One2many(
        "thread.lot.control.line",
        "control_id",
        string="Bags",
        copy=True,
    )
    bag_count = fields.Integer(string="Bag Count", compute="_compute_totals", store=True)
    cone_count = fields.Integer(string="Cone Count", compute="_compute_totals", store=True)
    total_weight = fields.Float(string="Total Weight (kg)", compute="_compute_totals", store=True, digits=(16, 3))
    average_cone_weight = fields.Float(
        string="Avg Cone Weight (kg)",
        compute="_compute_totals",
        store=True,
        digits=(16, 4),
    )
    note = fields.Text(string="Notes")

    @api.depends("line_ids.bag_qty", "line_ids.cone_qty", "line_ids.total_weight")
    def _compute_totals(self):
        for rec in self:
            rec.bag_count = int(sum(rec.line_ids.mapped("bag_qty")))
            rec.cone_count = int(sum((line.bag_qty or 0) * (line.cone_qty or 0) for line in rec.line_ids))
            rec.total_weight = float(sum(rec.line_ids.mapped("total_weight")))
            rec.average_cone_weight = rec.total_weight / rec.cone_count if rec.cone_count else 0.0

    @api.constrains("lot_id")
    def _check_thread_lot(self):
        for rec in self:
            if rec.lot_id and not rec.lot_id.product_id.is_thread:
                raise ValidationError("Only thread products are allowed in this control.")

    @api.model_create_multi
    def create(self, vals_list):
        seq = self.env["ir.sequence"]
        for vals in vals_list:
            if vals.get("name", "New") == "New":
                vals["name"] = seq.next_by_code("thread.lot.control") or "New"
            vals.setdefault("movement_type", "manual")
        return super().create(vals_list)


class ThreadLotControlLine(models.Model):
    _name = "thread.lot.control.line"
    _description = "Thread Lot Bag Control Line"
    _order = "id asc"

    control_id = fields.Many2one(
        "thread.lot.control",
        string="Control",
        required=True,
        ondelete="cascade",
        index=True,
    )
    date = fields.Date(
        string="Date",
        related="control_id.date",
        readonly=True,
    )
    movement_type = fields.Selection(
        related="control_id.movement_type",
        string="Tipo Movimiento",
        readonly=True,
    )
    lot_id = fields.Many2one(
        "stock.lot",
        string="Lot",
        related="control_id.lot_id",
        readonly=True,
    )
    product_id = fields.Many2one(
        "product.product",
        string="Product",
        related="control_id.product_id",
        readonly=True,
    )
    source_location_id = fields.Many2one(
        "stock.location",
        string="Source Location",
        related="control_id.source_location_id",
        readonly=True,
    )
    dest_location_id = fields.Many2one(
        "stock.location",
        string="Destination Location",
        related="control_id.dest_location_id",
        readonly=True,
    )
    bag_qty = fields.Integer(string="Bag Qty", required=True, default=1)
    cone_qty = fields.Integer(string="Cone Qty per Bag", required=True, default=0)
    total_weight = fields.Float(string="Bag Weight (kg)", default=0.0, digits=(16, 3))
    # Calculado desde total_weight / (bolsas × conos) — se almacena para consultas de disponibilidad.
    cone_weight = fields.Float(
        string="Cone Weight (kg)",
        compute="_compute_cone_weight",
        store=True,
        digits=(16, 4),
    )

    @api.depends("total_weight", "bag_qty", "cone_qty")
    def _compute_cone_weight(self):
        for rec in self:
            bags = rec.bag_qty or 0
            cones = rec.cone_qty or 0
            weight = rec.total_weight or 0.0
            if bags > 0 and cones > 0 and weight > 0:
                rec.cone_weight = weight / (bags * cones)
            else:
                rec.cone_weight = 0.0

    @api.constrains("bag_qty", "cone_qty", "total_weight")
    def _check_positive_values(self):
        for rec in self:
            if rec.bag_qty <= 0:
                raise ValidationError("Bag quantity must be greater than 0.")
            if rec.cone_qty < 0:
                raise ValidationError("Cone quantity cannot be negative.")
            if rec.total_weight < 0:
                raise ValidationError("Total weight cannot be negative.")
