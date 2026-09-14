# Copyright 2018 ForgeFlow S.L.
#   (http://www.forgeflow.com)
# Copyright 2026 Codex Development
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl.html).


from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    stock_request_allow_virtual_loc = fields.Boolean(
        string="Allow Virtual locations on Stock Requests"
    )
    stock_request_check_available_first = fields.Boolean(
        string="Check available stock first"
    )
    stock_request_direct_transfer = fields.Boolean(
        string="Create internal transfer when no route is selected",
        default=True,
        help="When no route is selected and the requested location is not the "
        "stock location of the warehouse, the request creates an internal "
        "transfer from the warehouse stock instead of running the product "
        "routes (buy / manufacture).",
    )
