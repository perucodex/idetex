# Copyright 2018 ForgeFlow, S.L.
# Copyright 2026 Codex Development
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl.html).

from odoo import api, fields, models
from odoo.exceptions import ValidationError


class StockWarehouse(models.Model):
    _inherit = "stock.warehouse"

    stock_request_location_id = fields.Many2one(
        "stock.location",
        string="Default request destination",
        check_company=True,
        domain="[('usage', 'in', ['internal', 'transit']), ('id', '!=', lot_stock_id)]",
        help="Location proposed as destination of the warehouse requests of this "
        "warehouse (e.g. Pre-Production, Workshop). Leave empty to force the "
        "requester to choose one. The stock location itself is never proposed "
        "because it is the source of the transfer.",
    )

    def _get_stock_request_default_location(self):
        """Destination proposed to a new request of this warehouse."""
        self.ensure_one()
        if self.company_id.stock_request_direct_transfer:
            return self.stock_request_location_id
        return self.lot_stock_id

    @api.constrains("company_id")
    def _check_company_stock_request(self):
        if any(
            self.env["stock.request"]
            .sudo()
            .search(
                [
                    ("company_id", "!=", rec.company_id.id),
                    ("warehouse_id", "=", rec.id),
                ],
                limit=1,
            )
            for rec in self
        ):
            raise ValidationError(
                self.env._(
                    "You cannot change the company of the warehouse, as it is "
                    "already assigned to stock requests that belong to "
                    "another company."
                )
            )
        if any(
            self.env["stock.request.order"]
            .sudo()
            .search(
                [
                    ("company_id", "!=", rec.company_id.id),
                    ("warehouse_id", "=", rec.id),
                ],
                limit=1,
            )
            for rec in self
        ):
            raise ValidationError(
                self.env._(
                    "You cannot change the company of the warehouse, as it is "
                    "already assigned to stock request orders that belong to "
                    "another company."
                )
            )
