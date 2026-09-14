# Copyright 2026 Codex Development
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl.html).

from odoo import Command, exceptions
from odoo.tests import new_test_user, tagged

from odoo.addons.base.tests.common import BaseCommon


@tagged("post_install", "-at_install")
class TestDirectTransfer(BaseCommon):
    """Requests to a location other than the warehouse stock create an
    internal transfer directly (no product routes involved)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.ref("base.main_company")
        cls.company.stock_request_direct_transfer = True
        cls.warehouse = cls.env["stock.warehouse"].search(
            [("company_id", "=", cls.company.id)], limit=1
        )
        cls.stock_loc = cls.warehouse.lot_stock_id
        cls.dest_loc = cls.env["stock.location"].create(
            {
                "name": "Taller Mantenimiento",
                "usage": "internal",
                "location_id": cls.warehouse.view_location_id.id,
                "company_id": cls.company.id,
            }
        )
        cls.product = cls.env["product.product"].create(
            {
                "name": "Guantes de nitrilo",
                "type": "consu",
                "is_storable": True,
                # a manufacture-like route must NOT be used by the request
                "route_ids": [
                    Command.set(
                        cls.env["stock.route"]
                        .search([("product_selectable", "=", True)], limit=1)
                        .ids
                    )
                ],
            }
        )
        cls.env["stock.quant"]._update_available_quantity(
            cls.product, cls.stock_loc, 10
        )
        cls.requester = new_test_user(
            cls.env,
            login="idtx_requester",
            groups="idtx_stock_request.group_stock_request_user",
        )

    def _create_order(self, qty=4, location=None, route=None, note=False):
        location = location or self.dest_loc
        line_vals = {
            "product_id": self.product.id,
            "product_uom_id": self.product.uom_id.id,
            "product_uom_qty": qty,
            "warehouse_id": self.warehouse.id,
            "location_id": location.id,
            "company_id": self.company.id,
        }
        if route:
            line_vals["route_id"] = route.id
        order = (
            self.env["stock.request.order"]
            .with_user(self.requester)
            .create(
                {
                    "warehouse_id": self.warehouse.id,
                    "location_id": location.id,
                    "company_id": self.company.id,
                    "note": note,
                    "stock_request_ids": [Command.create(line_vals)],
                }
            )
        )
        return order

    def test_order_creates_ready_internal_transfer(self):
        order = self._create_order(note="Para la máquina 3\nurgente")
        order.with_user(self.requester).action_confirm()
        order = order.sudo()
        self.assertEqual(order.state, "open")
        picking = order.picking_ids
        self.assertEqual(len(picking), 1)
        self.assertEqual(picking.picking_type_id, self.warehouse.int_type_id)
        self.assertEqual(picking.location_id, self.stock_loc)
        self.assertEqual(picking.location_dest_id, self.dest_loc)
        self.assertEqual(picking.origin, order.name)
        self.assertEqual(picking.partner_id, self.requester.partner_id)
        self.assertEqual(picking.state, "assigned", "stock reserved: ready")
        self.assertEqual(picking.reference_ids.name, order.name)
        self.assertIn("Para la máquina 3", picking.note)
        self.assertIn("urgente", picking.note)
        request = order.stock_request_ids
        self.assertEqual(request.state, "open")
        self.assertEqual(request.qty_in_progress, 4)
        self.assertEqual(request.picking_ids, picking)
        # the warehouse serves the transfer -> request and order are done
        picking.move_ids.quantity = 4
        picking.move_ids.picked = True
        picking.button_validate()
        self.assertEqual(picking.state, "done")
        self.assertEqual(request.qty_done, 4)
        self.assertEqual(request.state, "done")
        self.assertEqual(order.state, "done")

    def test_lines_of_one_order_share_the_transfer(self):
        product2 = self.env["product.product"].create(
            {"name": "Trapo industrial", "type": "consu", "is_storable": True}
        )
        order = self._create_order()
        order.sudo().write(
            {
                "stock_request_ids": [
                    Command.create(
                        {
                            "product_id": product2.id,
                            "product_uom_id": product2.uom_id.id,
                            "product_uom_qty": 2,
                            "warehouse_id": self.warehouse.id,
                            "location_id": self.dest_loc.id,
                            "company_id": self.company.id,
                        }
                    )
                ]
            }
        )
        order.sudo().action_confirm()
        order = order.sudo()
        self.assertEqual(len(order.picking_ids), 1)
        self.assertEqual(len(order.picking_ids.move_ids), 2)
        # product2 has no stock: transfer partially ready, request open
        line2 = order.stock_request_ids.filtered(lambda r: r.product_id == product2)
        self.assertEqual(line2.qty_in_progress, 2)
        self.assertEqual(order.state, "open")

    def test_cancel_request_cancels_transfer(self):
        order = self._create_order()
        order.sudo().action_confirm()
        order = order.sudo()
        picking = order.picking_ids
        order.action_cancel()
        self.assertEqual(picking.state, "cancel")
        self.assertEqual(order.state, "cancel")

    def test_request_to_stock_location_uses_routes(self):
        """Requesting *to* the stock location means replenishing the
        warehouse: the product routes apply (no direct transfer)."""
        route = self.env["stock.route"].create(
            {
                "name": "Recepción directa (test)",
                "company_id": self.company.id,
                "product_selectable": True,
            }
        )
        rule = self.env["stock.rule"].create(
            {
                "name": "Proveedores -> Stock",
                "route_id": route.id,
                "action": "pull",
                "picking_type_id": self.warehouse.in_type_id.id,
                "location_src_id": self.env.ref("stock.stock_location_suppliers").id,
                "location_dest_id": self.stock_loc.id,
                "warehouse_id": self.warehouse.id,
                "company_id": self.company.id,
                "procure_method": "make_to_stock",
            }
        )
        self.product.route_ids = [Command.set(route.ids)]
        order = self._create_order(location=self.stock_loc)
        order.with_user(self.requester).action_confirm()
        order = order.sudo()
        picking = order.picking_ids
        self.assertEqual(len(picking), 1)
        self.assertEqual(picking.picking_type_id, self.warehouse.in_type_id)
        self.assertEqual(picking.move_ids.rule_id, rule)

    def test_request_to_stock_location_is_refused(self):
        """Destination = stock location (the source) without a transfer rule:
        clear error instead of silently running the product routes."""
        self.product.route_ids = [Command.clear()]
        self.warehouse.reception_route_id.rule_ids.action = "push"
        order = self._create_order(location=self.stock_loc)
        with self.assertRaisesRegex(exceptions.UserError, "stock location"):
            order.sudo().action_confirm()
        self.assertEqual(order.state, "draft")

    def test_default_destination(self):
        """The stock location is never proposed with direct transfers; the
        warehouse can define the location proposed to requesters."""
        Order = self.env["stock.request.order"].with_user(self.requester)
        defaults = Order.default_get(["company_id", "warehouse_id", "location_id"])
        self.assertEqual(defaults.get("warehouse_id"), self.warehouse.id)
        self.assertFalse(defaults.get("location_id"))
        self.warehouse.stock_request_location_id = self.dest_loc
        defaults = Order.default_get(["company_id", "warehouse_id", "location_id"])
        self.assertEqual(defaults.get("location_id"), self.dest_loc.id)
        # onchange of the warehouse follows the same rule
        order = Order.new({"warehouse_id": self.warehouse.id, "company_id": self.company.id})
        order.onchange_warehouse_id()
        self.assertEqual(order.location_id, self.dest_loc)
        # OCA behaviour is kept when direct transfers are disabled
        self.company.stock_request_direct_transfer = False
        defaults = Order.default_get(["company_id", "warehouse_id", "location_id"])
        self.assertEqual(defaults.get("location_id"), self.stock_loc.id)

    def test_direct_transfer_disabled(self):
        self.company.stock_request_direct_transfer = False
        self.product.route_ids = [Command.clear()]
        order = self._create_order()
        with self.assertRaises(exceptions.UserError):
            order.sudo().action_confirm()

    def test_manufacture_route_is_ignored(self):
        """A product with a manufacture rule reaching the destination must
        still be served from stock, never with a manufacturing order."""
        actions = dict(self.env["stock.rule"]._fields["action"].selection)
        if "manufacture" not in actions:
            self.skipTest("mrp is not installed: no manufacture rules")
        route = self.env["stock.route"].create(
            {
                "name": "Fabricar (test)",
                "company_id": self.company.id,
                "product_selectable": True,
            }
        )
        self.env["stock.rule"].create(
            {
                "name": "Fabricar -> Stock",
                "route_id": route.id,
                "action": "manufacture",
                "picking_type_id": self.warehouse.int_type_id.id,
                "location_dest_id": self.stock_loc.id,
                "warehouse_id": self.warehouse.id,
                "company_id": self.company.id,
            }
        )
        self.product.route_ids = [Command.set(route.ids)]
        bin_loc = self.env["stock.location"].create(
            {
                "name": "Pesado",
                "usage": "internal",
                "location_id": self.stock_loc.id,
                "company_id": self.company.id,
            }
        )
        order = self._create_order(location=bin_loc)
        self.assertEqual(
            order.stock_request_ids.sudo()._get_applicable_rule().action,
            "manufacture",
        )
        order.sudo().action_confirm()
        order = order.sudo()
        picking = order.picking_ids
        self.assertEqual(len(picking), 1)
        self.assertEqual(picking.picking_type_id, self.warehouse.int_type_id)
        self.assertEqual(picking.location_dest_id, bin_loc)
        self.assertFalse(picking.move_ids.rule_id)

    def _create_pull_route(self, name="Reposición taller"):
        route = self.env["stock.route"].create(
            {
                "name": name,
                "company_id": self.company.id,
                "warehouse_selectable": True,
                "warehouse_ids": [Command.set(self.warehouse.ids)],
            }
        )
        rule = self.env["stock.rule"].create(
            {
                "name": "Stock -> Taller",
                "route_id": route.id,
                "action": "pull",
                "picking_type_id": self.warehouse.int_type_id.id,
                "location_src_id": self.stock_loc.id,
                "location_dest_id": self.dest_loc.id,
                "warehouse_id": self.warehouse.id,
                "company_id": self.company.id,
                "procure_method": "make_to_stock",
            }
        )
        return route, rule

    def test_route_one_transfer_per_request(self):
        """Through the routes, all the lines of a request share one transfer
        (even when the first line gets reserved at confirmation) and two
        requests never share a transfer."""
        route, rule = self._create_pull_route()
        product2 = self.env["product.product"].create(
            {"name": "Trapo industrial", "type": "consu", "is_storable": True}
        )
        self.env["stock.quant"]._update_available_quantity(
            product2, self.stock_loc, 10
        )
        self.assertEqual(self.warehouse.int_type_id.reservation_method, "at_confirm")
        order = self._create_order(route=route)
        order.sudo().write(
            {
                "stock_request_ids": [
                    Command.create(
                        {
                            "product_id": product2.id,
                            "product_uom_id": product2.uom_id.id,
                            "product_uom_qty": 2,
                            "warehouse_id": self.warehouse.id,
                            "location_id": self.dest_loc.id,
                            "company_id": self.company.id,
                            "route_id": route.id,
                        }
                    )
                ]
            }
        )
        order.with_user(self.requester).action_confirm()
        order = order.sudo()
        picking = order.picking_ids
        self.assertEqual(len(picking), 1)
        self.assertEqual(len(picking.move_ids), 2)
        self.assertEqual(picking.state, "assigned")
        self.assertEqual(picking.move_ids.rule_id, rule)
        self.assertEqual(order.request_reference_id.name, order.name)
        self.assertEqual(picking.reference_ids, order.request_reference_id)
        # a second request to the same place gets its own transfer
        order2 = self._create_order(route=route)
        order2.sudo().action_confirm()
        order2 = order2.sudo()
        self.assertEqual(len(order2.picking_ids), 1)
        self.assertNotEqual(order2.picking_ids, picking)

    def test_print_report(self):
        order = self._create_order(note="Para la máquina 3")
        html, _type = (
            self.env["ir.actions.report"]
            .with_user(self.requester)
            ._render_qweb_html("idtx_stock_request.report_stock_request_order", order.ids)
        )
        html = html.decode()
        self.assertIn("REQUERIMIENTO DE PRODUCTOS", html)
        self.assertIn(order.name, html)
        self.assertIn(self.product.display_name, html)
        self.assertIn("PARA LA MÁQUINA 3", html)
        self.assertIn(self.dest_loc.name.upper(), html)
        self.assertRegex(order._report_date_label(), r"^\d{2}/[A-Z][a-z]+/\d{4}$")
        self.assertEqual(order.stock_request_ids._report_qty(), "4")

    def test_selected_route_wins(self):
        route, rule = self._create_pull_route()
        order = self._create_order(route=route)
        order.sudo().action_confirm()
        order = order.sudo()
        self.assertEqual(len(order.picking_ids), 1)
        self.assertEqual(order.picking_ids.move_ids.rule_id, rule)
