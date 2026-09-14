# Copyright 2017-2020 ForgeFlow, S.L.
# Copyright 2026 Codex Development
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl.html).

from markupsafe import Markup

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_compare


class StockRequest(models.Model):
    _name = "stock.request"
    _description = "Stock Request"
    _inherit = "stock.request.abstract"
    _order = "id desc"

    def _get_default_requested_by(self):
        return self.env["res.users"].browse(self.env.uid)

    @staticmethod
    def _get_expected_date():
        return fields.Datetime.now()

    name = fields.Char()
    state = fields.Selection(
        selection=[
            ("draft", "Draft"),
            ("open", "In progress"),
            ("done", "Done"),
            ("cancel", "Cancelled"),
        ],
        string="Status",
        copy=False,
        default="draft",
        index=True,
        readonly=True,
        tracking=True,
    )
    requested_by = fields.Many2one(
        "res.users",
        required=True,
        tracking=True,
        default=lambda s: s._get_default_requested_by(),
    )
    expected_date = fields.Datetime(
        index=True,
        required=True,
        help="Date when you expect to receive the goods.",
    )
    picking_policy = fields.Selection(
        [
            ("direct", "Receive each product when available"),
            ("one", "Receive all products at once"),
        ],
        string="Shipping Policy",
        required=True,
        default="direct",
    )
    move_ids = fields.One2many(
        comodel_name="stock.move",
        compute="_compute_move_ids",
        string="Stock Moves",
        readonly=True,
    )
    picking_ids = fields.One2many(
        "stock.picking",
        compute="_compute_picking_ids",
        string="Pickings",
        readonly=True,
    )
    qty_in_progress = fields.Float(
        digits="Product Unit of Measure",
        readonly=True,
        compute="_compute_qty",
        store=True,
        help="Quantity in progress.",
    )
    qty_done = fields.Float(
        digits="Product Unit of Measure",
        readonly=True,
        compute="_compute_qty",
        store=True,
        help="Quantity completed",
    )
    qty_cancelled = fields.Float(
        digits="Product Unit of Measure",
        readonly=True,
        compute="_compute_qty",
        store=True,
        help="Quantity cancelled",
    )
    picking_count = fields.Integer(
        string="Delivery Orders",
        compute="_compute_picking_ids",
        readonly=True,
    )
    allocation_ids = fields.One2many(
        comodel_name="stock.request.allocation",
        inverse_name="stock_request_id",
        string="Stock Request Allocation",
    )
    order_id = fields.Many2one("stock.request.order", readonly=True)
    request_reference_id = fields.Many2one(
        "stock.reference",
        string="Stock reference",
        readonly=True,
        copy=False,
        help="Reference used to group the moves of a stand-alone request "
        "(requests of an order use the reference of the order).",
    )
    warehouse_id = fields.Many2one()
    location_id = fields.Many2one()
    product_id = fields.Many2one()
    product_uom_id = fields.Many2one()
    product_uom_qty = fields.Float()
    reference_ids = fields.Many2many()
    company_id = fields.Many2one()
    route_id = fields.Many2one()

    _name_uniq = models.Constraint(
        "unique(name, company_id)", "Stock Request name must be unique"
    )

    @api.constrains("state", "product_qty")
    def _check_qty(self):
        for rec in self:
            if rec.state == "draft" and rec.product_qty <= 0:
                raise ValidationError(
                    self.env._(
                        "Stock Request product quantity has to be strictly positive."
                    )
                )
            elif rec.state != "draft" and rec.product_qty < 0:
                raise ValidationError(
                    self.env._("Stock Request product quantity cannot be negative.")
                )

    def _get_all_origin_moves(self, move):
        # Collect the move and all its transitive origin moves. The traversal
        # is iterative and keeps track of the moves already visited because
        # ``move_orig_ids`` can form a cyclic graph (e.g. returning both legs
        # of a two-step inter-warehouse transfer that share a transit
        # location links each leg's return to the other). A naive recursion
        # over such a cycle raises RecursionError.
        all_moves = self.env["stock.move"]
        moves_to_visit = move
        while moves_to_visit:
            moves_to_visit -= all_moves
            all_moves |= moves_to_visit
            moves_to_visit = moves_to_visit.move_orig_ids
        return all_moves

    @api.depends("allocation_ids", "allocation_ids.stock_move_id")
    def _compute_move_ids(self):
        for request in self:
            move_ids = request.allocation_ids.mapped("stock_move_id")
            all_moves = self.env["stock.move"]
            for move in move_ids:
                all_moves |= self._get_all_origin_moves(move)
            request.move_ids = all_moves

    @api.depends(
        "allocation_ids",
        "allocation_ids.stock_move_id",
        "allocation_ids.stock_move_id.picking_id",
    )
    def _compute_picking_ids(self):
        for request in self:
            request.picking_count = 0
            request.picking_ids = self.env["stock.picking"]
            request.picking_ids = request.move_ids.filtered(
                lambda m: m.state != "cancel"
            ).mapped("picking_id")
            request.picking_count = len(request.picking_ids)

    @api.depends(
        "allocation_ids",
        "allocation_ids.stock_move_id.state",
        "allocation_ids.stock_move_id.move_line_ids",
        "allocation_ids.stock_move_id.move_line_ids.quantity",
    )
    def _compute_qty(self):
        for request in self:
            incoming_qty = 0.0
            other_qty = 0.0
            for allocation in request.allocation_ids:
                if allocation.stock_move_id.picking_code == "incoming":
                    incoming_qty += allocation.allocated_product_qty
                else:
                    other_qty += allocation.allocated_product_qty
            done_qty = abs(other_qty - incoming_qty)
            open_qty = sum(request.allocation_ids.mapped("open_product_qty"))
            uom = request.product_id.uom_id
            request.qty_done = uom._compute_quantity(
                done_qty,
                request.product_uom_id,
                rounding_method="HALF-UP",
            )
            request.qty_in_progress = uom._compute_quantity(
                open_qty,
                request.product_uom_id,
                rounding_method="HALF-UP",
            )
            request.qty_cancelled = (
                max(
                    0,
                    uom._compute_quantity(
                        request.product_qty - done_qty - open_qty,
                        request.product_uom_id,
                        rounding_method="HALF-UP",
                    ),
                )
                if request.allocation_ids
                else 0
            )

    @api.constrains("order_id", "requested_by")
    def check_order_requested_by(self):
        for stock_request in self:
            if (
                stock_request.order_id
                and stock_request.order_id.requested_by != stock_request.requested_by
            ):
                raise ValidationError(
                    self.env._("Requested by must be equal to the order")
                )

    @api.constrains("order_id", "warehouse_id")
    def check_order_warehouse_id(self):
        for stock_request in self:
            if (
                stock_request.order_id
                and stock_request.order_id.warehouse_id != stock_request.warehouse_id
            ):
                raise ValidationError(
                    self.env._("Warehouse must be equal to the order")
                )

    @api.constrains("order_id", "location_id")
    def check_order_location(self):
        for stock_request in self:
            if (
                stock_request.order_id
                and stock_request.order_id.location_id != stock_request.location_id
            ):
                raise ValidationError(self.env._("Location must be equal to the order"))

    @api.constrains("order_id", "reference_ids")
    def check_order_reference_ids(self):
        for stock_request in self:
            if (
                stock_request.order_id
                and stock_request.order_id.reference_ids != stock_request.reference_ids
            ):
                raise ValidationError(
                    self.env._("References must be equal to the order")
                )

    @api.constrains("order_id", "company_id")
    def check_order_company(self):
        for stock_request in self:
            if (
                stock_request.order_id
                and stock_request.order_id.company_id != stock_request.company_id
            ):
                raise ValidationError(self.env._("Company must be equal to the order"))

    @api.constrains("order_id", "expected_date")
    def check_order_expected_date(self):
        for stock_request in self:
            if (
                stock_request.order_id
                and stock_request.order_id.expected_date != stock_request.expected_date
            ):
                raise ValidationError(
                    self.env._("Expected date must be equal to the order")
                )

    @api.constrains("order_id", "picking_policy")
    def check_order_picking_policy(self):
        for stock_request in self:
            if (
                stock_request.order_id
                and stock_request.order_id.picking_policy
                != stock_request.picking_policy
            ):
                raise ValidationError(
                    self.env._("The picking policy must be equal to the order")
                )

    def _action_confirm(self):
        self._action_launch_procurement_rule()
        self.filtered(lambda x: x.state != "done").write({"state": "open"})

    def action_confirm(self):
        self._action_confirm()
        return True

    def action_draft(self):
        self.write({"state": "draft"})
        return True

    def action_cancel(self):
        self.sudo().mapped("move_ids")._action_cancel()
        self.write({"state": "cancel"})
        return True

    def action_done(self):
        self.write({"state": "done"})
        return True

    def check_cancel(self):
        for request in self:
            if request._check_cancel_allocation():
                request.write({"state": "cancel"})

    def check_done(self):
        precision = self.env["decimal.precision"].precision_get(
            "Product Unit of Measure"
        )
        for request in self:
            allocated_qty = sum(request.allocation_ids.mapped("allocated_product_qty"))
            qty_done = request.product_id.uom_id._compute_quantity(
                allocated_qty, request.product_uom_id
            )
            if (
                float_compare(
                    qty_done, request.product_uom_qty, precision_digits=precision
                )
                >= 0
            ):
                request.action_done()
            elif request._check_cancel_allocation():
                # If qty_done=0 and qty_cancelled>0 it's cancelled
                request.write({"state": "cancel"})
        return True

    def _check_cancel_allocation(self):
        precision = self.env["decimal.precision"].precision_get(
            "Product Unit of Measure"
        )
        self.ensure_one()
        return (
            self.allocation_ids
            and float_compare(self.qty_cancelled, 0, precision_digits=precision) > 0
        )

    def _prepare_procurement_values(self, reference_ids=False):
        """Prepare specific key for moves or other components that
        will be created from a procurement rule
        coming from a stock request. This method could be override
        in order to add other custom key that could be used in
        move/po creation.
        """
        # One transfer per request: without an explicit reference, the moves
        # of a request would not share a picking (Odoo 19 only merges moves
        # into an existing picking when they carry the same references), so
        # every request (order) gets its own stock.reference.
        return {
            "date_planned": self.expected_date,
            "warehouse_id": self.warehouse_id,
            "stock_request_allocation_ids": self.id,
            "reference_ids": reference_ids
            or self.reference_ids
            or self._get_request_reference(),
            "route_ids": self.route_id,
            "stock_request_id": self.id,
        }

    def _get_request_reference(self):
        """stock.reference shared by all the lines of the request order (or
        owned by the request when it does not belong to an order)."""
        self.ensure_one()
        document = (self.order_id or self).sudo()
        if not document.request_reference_id:
            document.request_reference_id = (
                self.env["stock.reference"].sudo().create({"name": document.name})
            )
        return document.request_reference_id

    def _skip_procurement(self):
        return self.state != "draft" or self.product_id.type not in ("consu", "product")

    def _prepare_stock_move(self, qty):
        return {
            "company_id": self.company_id.id,
            "product_id": self.product_id.id,
            "product_uom_qty": qty,
            "product_uom": self.product_id.uom_id.id,
            "location_id": self.location_id.id,
            "location_dest_id": self.location_id.id,
            "state": "draft",
            "reference": self.name,
        }

    def _prepare_stock_request_allocation(self, move):
        return {
            "stock_request_id": self.id,
            "stock_move_id": move.id,
            "requested_product_uom_qty": move.product_uom_qty,
        }

    def _action_use_stock_available(self):
        """Create a stock move with the necessary data and mark it as done."""
        allocation_model = self.env["stock.request.allocation"]
        stock_move_model = self.env["stock.move"].sudo()
        precision = self.env["decimal.precision"].precision_get(
            "Product Unit of Measure"
        )
        quants = self.env["stock.quant"]._gather(self.product_id, self.location_id)
        pending_qty = self.product_uom_qty
        for quant in quants.filtered(lambda x: x.available_quantity >= 0):
            qty_move = min(pending_qty, quant.available_quantity)
            if float_compare(qty_move, 0, precision_digits=precision) > 0:
                move = stock_move_model.create(self._prepare_stock_move(qty_move))
                move._action_confirm()
                pending_qty -= qty_move
                # Create allocation + done move
                allocation_model.create(self._prepare_stock_request_allocation(move))
                move.quantity = move.product_uom_qty
                move.picked = True
                move._action_done()

    def _action_launch_procurement_rule(self):
        """
        Launch stock rule (if not enough stock is available) run method
        with required/custom fields genrated by a
        stock request. stock rule will launch '_run_move',
        '_run_buy' or '_run_manufacture'
        depending on the stock request product rule.
        """
        precision = self.env["decimal.precision"].precision_get(
            "Product Unit of Measure"
        )
        errors = []
        direct_requests = self.env["stock.request"]
        procurements = []
        for request in self:
            if request._skip_procurement():
                continue
            qty = 0.0
            for move in request.move_ids.filtered(lambda r: r.state != "cancel"):
                qty += move.product_qty

            if float_compare(qty, request.product_qty, precision_digits=precision) >= 0:
                continue

            # If stock is available we use it and we do not execute rule
            if request.company_id.stock_request_check_available_first:
                if (
                    float_compare(
                        request.product_id.sudo()
                        .with_context(location=request.location_id.id)
                        .free_qty,
                        request.product_uom_qty,
                        precision_digits=precision,
                    )
                    >= 0
                ):
                    request._action_use_stock_available()
                    continue

            if request._use_direct_transfer():
                direct_requests |= request
                continue
            request._check_direct_transfer_destination()

            # sudo like the direct transfer: the requester usually has no
            # rights on rules, BoMs (mrp kits) or transfers. The records
            # inside the procurement must be sudo too (mrp reads bom_ids).
            request_su = request.sudo()
            values = request_su._prepare_procurement_values(
                reference_ids=request_su.reference_ids
            )
            procurements.append(
                request_su.env["stock.rule"].Procurement(
                    request_su.product_id,
                    request_su.product_uom_qty,
                    request_su.product_uom_id,
                    request_su.location_id,
                    request_su.name,
                    request_su.name,
                    self.env.company,
                    values,
                )
            )
        if direct_requests:
            direct_requests._action_create_direct_transfer()
        if procurements:
            # a single run: the moves of all the lines are created and
            # confirmed together, so they land in the same transfer
            try:
                self.env["stock.rule"].sudo().run(procurements)
            except UserError as error:
                errors.append(str(error))
        if errors:
            raise UserError("\n".join(errors))
        return True

    # ------------------------------------------------------------------
    # Direct internal transfer (IDETEX)
    # ------------------------------------------------------------------
    def _get_direct_transfer_picking_type(self):
        self.ensure_one()
        return self.warehouse_id.int_type_id

    def _get_direct_transfer_source_location(self):
        self.ensure_one()
        return self.warehouse_id.lot_stock_id

    def _get_applicable_rule(self):
        """Rule the stock rules engine would pick for this request (same
        lookup as ``stock.rule.run``), or an empty recordset."""
        self.ensure_one()
        values = self._prepare_procurement_values(reference_ids=self.reference_ids)
        values.setdefault("company_id", self.company_id)
        # sudo: the lookup reads routes / BoMs the requester may not access
        request = self.sudo()
        return request.env["stock.rule"]._get_rule(
            request.product_id, request.location_id, values
        )

    def _use_direct_transfer(self):
        """Return True when the request must be served with an internal
        transfer from the warehouse stock location instead of the routes.

        This is the case when the company enables it, the requester did not
        select a route, the requested location is not the stock location of
        the warehouse itself (a request *to* the stock location means
        replenishing the warehouse, which is left to the product routes) and
        no *transfer* rule (pull) applies to the location. A buy or
        manufacture rule coming from the product routes is ignored: a
        warehouse request never creates purchase or manufacturing orders.
        """
        self.ensure_one()
        if self.route_id or not self.company_id.stock_request_direct_transfer:
            return False
        picking_type = self._get_direct_transfer_picking_type()
        source = self._get_direct_transfer_source_location()
        if not picking_type or not source or source == self.location_id:
            return False
        rule = self._get_applicable_rule()
        return not rule or rule.action not in ("pull", "pull_push")

    def _check_direct_transfer_destination(self):
        """With direct transfers enabled, a request whose destination is the
        stock location of the warehouse (the source) and that has no transfer
        rule would silently fall into the product routes: in Odoo 19 a buy
        rule without vendor creates nothing and raises nothing. Fail loudly
        so the requester fixes the destination instead of waiting forever."""
        self.ensure_one()
        if self.route_id or not self.company_id.stock_request_direct_transfer:
            return
        if self.location_id != self._get_direct_transfer_source_location():
            return
        rule = self._get_applicable_rule()
        if rule and rule.action in ("pull", "pull_push"):
            return
        raise UserError(
            self.env._(
                "%(request)s: the destination %(location)s is the stock location "
                "of the warehouse, that is, where the products are taken from. "
                "Set the location where you need the products (e.g. "
                "Pre-Production, Workshop) or select a route.",
                request=self.name,
                location=self.location_id.display_name,
            )
        )

    def _get_direct_transfer_group_key(self):
        """Requests sharing this key are grouped in the same transfer."""
        self.ensure_one()
        return (
            ("order", self.order_id.id) if self.order_id else ("request", self.id),
            self._get_direct_transfer_picking_type().id,
            self._get_direct_transfer_source_location().id,
            self.location_id.id,
            self.company_id.id,
        )

    def _get_direct_transfer_note(self):
        self.ensure_one()
        note = self.order_id.note if self.order_id else False
        if not note:
            return False
        lines = [Markup.escape(line) for line in note.splitlines()]
        return Markup("<p>%s</p>") % Markup("<br/>").join(lines)

    def _prepare_direct_transfer_picking_values(self):
        self.ensure_one()
        document = self.order_id or self
        return {
            "picking_type_id": self._get_direct_transfer_picking_type().id,
            "location_id": self._get_direct_transfer_source_location().id,
            "location_dest_id": self.location_id.id,
            "company_id": self.company_id.id,
            "origin": document.name,
            "partner_id": self.requested_by.partner_id.id,
            "user_id": False,
            "scheduled_date": self.expected_date,
            "move_type": self.picking_policy,
            "note": self._get_direct_transfer_note(),
        }

    def _prepare_direct_transfer_move_values(self, picking):
        self.ensure_one()
        return {
            "product_id": self.product_id.id,
            "product_uom_qty": self.product_uom_qty,
            "product_uom": self.product_uom_id.id,
            "location_id": picking.location_id.id,
            "location_dest_id": picking.location_dest_id.id,
            "picking_id": picking.id,
            "picking_type_id": picking.picking_type_id.id,
            "warehouse_id": self.warehouse_id.id,
            "company_id": self.company_id.id,
            "origin": picking.origin,
            "date": self.expected_date,
            "date_deadline": self.expected_date,
            "procure_method": "make_to_stock",
            "reference_ids": [(4, self._get_request_reference().id)],
            "allocation_ids": [
                (
                    0,
                    0,
                    {
                        "stock_request_id": self.id,
                        "requested_product_uom_qty": self.product_uom_qty,
                    },
                )
            ],
        }

    def _action_create_direct_transfer(self):
        """Create the internal transfers (one per request order, or one per
        stand-alone request) from the warehouse stock to the requested
        location, confirm them and reserve the stock so they show up as
        *Ready* for the warehouse staff.

        Done with sudo like the stock rules do: the requester usually has no
        rights on transfers.
        """
        pickings = self.env["stock.picking"].sudo()
        moves = self.env["stock.move"].sudo()
        picking_by_key = {}
        for request in self:
            key = request._get_direct_transfer_group_key()
            picking = picking_by_key.get(key)
            if not picking:
                picking = (
                    self.env["stock.picking"]
                    .sudo()
                    .with_company(request.company_id)
                    .create(request._prepare_direct_transfer_picking_values())
                )
                picking_by_key[key] = picking
                pickings |= picking
            moves |= (
                self.env["stock.move"]
                .sudo()
                .with_company(request.company_id)
                .create(request._prepare_direct_transfer_move_values(picking))
            )
        moves._action_confirm()
        pickings.action_assign()
        return pickings

    def _report_qty(self):
        """Quantity without useless decimals for the printed form."""
        self.ensure_one()
        return ("%.3f" % self.product_uom_qty).rstrip("0").rstrip(".")

    def action_view_transfer(self):
        action = self.env["ir.actions.act_window"]._for_xml_id(
            "stock.action_picking_tree_all"
        )
        pickings = self.mapped("picking_ids")
        if len(pickings) > 1:
            action["domain"] = [("id", "in", pickings.ids)]
        elif pickings:
            action["views"] = [(self.env.ref("stock.view_picking_form").id, "form")]
            action["res_id"] = pickings.id
        return action

    @api.model_create_multi
    def create(self, vals_list):
        vals_list_upd = []
        for vals in vals_list:
            upd_vals = vals.copy()
            if upd_vals.get("name", "/") == "/":
                upd_vals["name"] = self.env["ir.sequence"].next_by_code("stock.request")
            if "order_id" in upd_vals:
                order_id = self.env["stock.request.order"].browse(upd_vals["order_id"])
                upd_vals["expected_date"] = order_id.expected_date
            else:
                upd_vals["expected_date"] = self._get_expected_date()
            vals_list_upd.append(upd_vals)
        return super().create(vals_list_upd)

    def _check_before_unlink(self):
        if self.filtered(lambda r: r.state != "draft"):
            raise UserError(self.env._("Only requests on draft state can be unlinked"))

    def unlink(self):
        self._check_before_unlink()
        return super().unlink()
