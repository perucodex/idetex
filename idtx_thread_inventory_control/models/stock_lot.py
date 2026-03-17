from odoo import fields, models


class StockLot(models.Model):
    _inherit = "stock.lot"

    thread_control_ids = fields.One2many(
        "thread.lot.control",
        "lot_id",
        string="Thread Controls",
    )
    thread_control_count = fields.Integer(
        string="Thread Control Count",
        compute="_compute_thread_control_count",
    )
    thread_in_bags = fields.Integer(string="In Bags", compute="_compute_thread_balances")
    thread_out_bags = fields.Integer(string="Out Bags", compute="_compute_thread_balances")
    thread_balance_bags = fields.Integer(string="Remaining Bags", compute="_compute_thread_balances")
    thread_in_cones = fields.Integer(string="In Cones", compute="_compute_thread_balances")
    thread_out_cones = fields.Integer(string="Out Cones", compute="_compute_thread_balances")
    thread_balance_cones = fields.Integer(string="Remaining Cones", compute="_compute_thread_balances")
    thread_in_weight = fields.Float(string="In Weight (kg)", compute="_compute_thread_balances", digits=(16, 3))
    thread_out_weight = fields.Float(string="Out Weight (kg)", compute="_compute_thread_balances", digits=(16, 3))
    thread_balance_weight = fields.Float(string="Remaining Weight (kg)", compute="_compute_thread_balances", digits=(16, 3))
    thread_second_quality_bags = fields.Integer(string="2nd Quality Bags", compute="_compute_thread_balances")
    thread_second_quality_cones = fields.Integer(string="2nd Quality Cones", compute="_compute_thread_balances")
    thread_second_quality_weight = fields.Float(string="2nd Quality Weight (kg)", compute="_compute_thread_balances", digits=(16, 3))

    def _compute_thread_control_count(self):
        grouped = self.env["thread.lot.control"].read_group(
            [("lot_id", "in", self.ids)],
            ["lot_id"],
            ["lot_id"],
        )
        count_map = {item["lot_id"][0]: item["lot_id_count"] for item in grouped if item.get("lot_id")}
        for lot in self:
            lot.thread_control_count = count_map.get(lot.id, 0)

    def action_open_thread_controls(self):
        self.ensure_one()
        return {
            "name": "Thread Bag Controls",
            "type": "ir.actions.act_window",
            "res_model": "thread.lot.control",
            "view_mode": "list,form",
            "domain": [("lot_id", "=", self.id)],
            "context": {
                "default_lot_id": self.id,
            },
        }

    def _compute_thread_balances(self):
        controls = self.env["thread.lot.control"]
        for lot in self:
            lot_controls = controls.search([("lot_id", "=", lot.id)])
            in_bags = 0
            out_bags = 0
            in_cones = 0
            out_cones = 0
            in_weight = 0.0
            out_weight = 0.0
            second_bags = 0
            second_cones = 0
            second_weight = 0.0

            for control in lot_controls:
                src = control.source_location_id
                dst = control.dest_location_id
                movement_type = control.movement_type

                bags = int(sum(control.line_ids.mapped("bag_qty")))
                cones = int(sum((line.bag_qty or 0) * (line.cone_qty or 0) for line in control.line_ids))
                weight = float(sum(control.line_ids.mapped("total_weight")))

                # Clasificacion principal por tipo de movimiento registrado en thread.lot.control.
                is_in_main = movement_type == "in"
                is_out_main = movement_type == "out"
                is_second_quality = movement_type == "balance"

                # Fallback para controles legacy sin tipo correcto.
                if movement_type in (False, "manual"):
                    is_in_main = bool(dst and dst.is_thread_main_location)
                    is_out_main = bool(src and src.is_thread_main_location)
                    is_second_quality = bool(dst and dst.is_thread_second_quality_location)

                    if not is_in_main and not is_out_main:
                        if not src and not dst:
                            is_in_main = True
                        elif dst and dst.usage == "internal" and (not src or src.usage != "internal"):
                            is_in_main = True
                        elif src and src.usage == "internal" and (not dst or dst.usage != "internal"):
                            is_out_main = True

                if is_in_main:
                    in_bags += bags
                    in_cones += cones
                    in_weight += weight
                if is_out_main:
                    out_bags += bags
                    out_cones += cones
                    out_weight += weight

                if is_second_quality:
                    second_bags += bags
                    second_cones += cones
                    second_weight += weight

            lot.thread_in_bags = in_bags
            lot.thread_out_bags = out_bags
            lot.thread_balance_bags = in_bags - out_bags
            lot.thread_in_cones = in_cones
            lot.thread_out_cones = out_cones
            lot.thread_balance_cones = in_cones - out_cones
            lot.thread_in_weight = in_weight
            lot.thread_out_weight = out_weight
            lot.thread_balance_weight = in_weight - out_weight

            lot.thread_second_quality_bags = second_bags
            lot.thread_second_quality_cones = second_cones
            lot.thread_second_quality_weight = second_weight
