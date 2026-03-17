import math

from odoo import _, models, fields
from odoo.exceptions import ValidationError


class MrpProduction(models.Model):
    _inherit = "mrp.production"

    @staticmethod
    def _thread_move_line_qty(move_line):
        qty = float(move_line.quantity or 0.0) if "quantity" in move_line._fields else 0.0
        if qty > 0:
            return qty
        if "qty_done" in move_line._fields:
            return float(move_line.qty_done or 0.0)
        return qty

    thread_liquidation_picking_ids = fields.One2many(
        "stock.picking",
        "thread_liquidation_production_id",
        string="Liquidaciones de Hilo",
    )
    thread_liquidation_count = fields.Integer(
        string="Liquidaciones Hilo",
        compute="_compute_thread_liquidation_count",
    )
    thread_liquidation_pending_qty = fields.Float(
        string="Kg Pendientes Liquidar",
        compute="_compute_thread_liquidation_pending_qty",
        digits=(16, 4),
    )
    can_liquidate_thread = fields.Boolean(
        string="Puede Liquidar Hilo",
        compute="_compute_thread_liquidation_pending_qty",
    )

    def _compute_thread_liquidation_count(self):
        for production in self:
            production.thread_liquidation_count = len(production.thread_liquidation_picking_ids)

    def _thread_get_source_location_for_liquidation(self):
        self.ensure_one()
        source_locations = self.env["stock.location"].search([
            ("is_thread_production_location", "=", True),
            "|", ("company_id", "=", self.company_id.id), ("company_id", "=", False),
        ])
        if len(source_locations) == 1:
            return source_locations[:1]

        done_thread_moves = self.picking_ids.filtered(lambda p: p.state == "done").move_ids.filtered(
            lambda m: m.product_id.is_thread and m.location_dest_id and m.location_dest_id.usage == "internal"
        )
        candidate_locs = done_thread_moves.mapped("location_dest_id")
        return candidate_locs[:1] if len(candidate_locs) == 1 else self.env["stock.location"]

    def _thread_get_configured_production_location(self):
        self.ensure_one()
        source_locations = self.env["stock.location"].search([
            ("is_thread_production_location", "=", True),
            "|", ("company_id", "=", self.company_id.id), ("company_id", "=", False),
        ])
        return source_locations[:1] if len(source_locations) == 1 else self.env["stock.location"]

    def _thread_align_raw_move_source_location(self):
        """Keep thread raw moves sourcing from thread production location.

        The lot picker in MO detailed operations filters stock.quants by
        move line source location (parent.location_id). If thread raw moves keep
        a different source location, the picker can appear empty even when stock
        is available in preproduction.
        """
        for production in self:
            target_location = production._thread_get_configured_production_location() or production.location_src_id
            if not target_location:
                continue

            moves = production.move_raw_ids.filtered(
                lambda m: m.product_id.is_thread and m.state not in ("done", "cancel")
            )
            for move in moves:
                old_location = move.location_id
                if old_location == target_location:
                    continue

                move.write({"location_id": target_location.id})
                line_domain = move.move_line_ids
                if old_location:
                    line_domain = line_domain.filtered(
                        lambda ml: not ml.location_id or ml.location_id == old_location
                    )
                if line_domain:
                    line_domain.write({"location_id": target_location.id})

    def _thread_get_liquidation_maps(self, source_location=False):
        self.ensure_one()
        consumed_map = {}
        for move in self.move_raw_ids.filtered(lambda m: m.product_id.is_thread):
            for move_line in move.move_line_ids:
                line_qty = self._thread_move_line_qty(move_line)
                if line_qty <= 0:
                    continue
                lot = move._resolve_thread_lot_from_line(move_line)
                if not lot:
                    continue
                key = (move_line.product_id.id, lot.id)
                consumed_map[key] = consumed_map.get(key, 0.0) + line_qty

        source_id = source_location.id if source_location else False
        received_map = {}
        for picking in self.picking_ids.filtered(lambda p: p.state == "done"):
            thread_moves = picking.move_ids.filtered(
                lambda m: m.product_id.is_thread and (not source_id or m.location_dest_id.id == source_id)
            )
            for move in thread_moves:
                for move_line in move.move_line_ids:
                    line_qty = self._thread_move_line_qty(move_line)
                    if line_qty <= 0:
                        continue
                    lot = move._resolve_thread_lot_from_line(move_line)
                    if not lot:
                        continue
                    key = (move_line.product_id.id, lot.id)
                    received_map[key] = received_map.get(key, 0.0) + line_qty

        liquidated_map = {}
        for picking in self.thread_liquidation_picking_ids.filtered(lambda p: p.state == "done"):
            thread_moves = picking.move_ids.filtered(
                lambda m: m.product_id.is_thread and (not source_id or m.location_id.id == source_id)
            )
            for move in thread_moves:
                for move_line in move.move_line_ids:
                    line_qty = self._thread_move_line_qty(move_line)
                    if line_qty <= 0:
                        continue
                    lot = move._resolve_thread_lot_from_line(move_line)
                    if not lot:
                        continue
                    key = (move_line.product_id.id, lot.id)
                    liquidated_map[key] = liquidated_map.get(key, 0.0) + line_qty

        return consumed_map, received_map, liquidated_map

    def _compute_thread_liquidation_pending_qty(self):
        for production in self:
            source_location = production._thread_get_source_location_for_liquidation()
            consumed_map, received_map, liquidated_map = production._thread_get_liquidation_maps(source_location=source_location)

            pending_qty = 0.0
            for key in (set(consumed_map.keys()) | set(received_map.keys()) | set(liquidated_map.keys())):
                received_qty = float(received_map.get(key, 0.0) or 0.0)
                consumed_qty = float(consumed_map.get(key, 0.0) or 0.0)
                liquidated_qty = float(liquidated_map.get(key, 0.0) or 0.0)
                balance_qty = max(received_qty - consumed_qty - liquidated_qty, 0.0)
                pending_qty += balance_qty

            production.thread_liquidation_pending_qty = pending_qty
            production.can_liquidate_thread = bool(pending_qty > 1e-6)

    def action_open_thread_second_quality_wizard(self):
        self.ensure_one()
        if not self.can_liquidate_thread:
            raise ValidationError(_("El saldo de hilo ya fue liquidado en su totalidad."))
        return {
            "name": _("Liquidar Hilado"),
            "type": "ir.actions.act_window",
            "res_model": "thread.second.quality.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_production_id": self.id,
            },
        }

    def action_view_thread_liquidations(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id("stock.action_picking_tree_internal")
        action["domain"] = [("thread_liquidation_production_id", "=", self.id)]
        action["context"] = {
            "default_thread_liquidation_production_id": self.id,
            "default_origin": "%s - Liquidacion Hilado" % self.name,
        }
        if self.thread_liquidation_count == 1:
            action["view_mode"] = "form"
            action["res_id"] = self.thread_liquidation_picking_ids.id
        return action

    def _thread_pick_combo_for_quantity(self, availability, qty):
        qty = float(qty or 0.0)
        if qty <= 0:
            return None

        cover_candidates = []
        partial_candidates = []
        for cones, weight_map in availability.items():
            for weight, available_bags in weight_map.items():
                if available_bags <= 0:
                    continue
                bag_weight = float(cones) * float(weight)
                if bag_weight <= 0:
                    continue

                needed_bags = int(math.ceil(qty / bag_weight))
                if needed_bags <= int(available_bags):
                    bag_qty = max(1, needed_bags)
                    produced_qty = float(bag_qty) * bag_weight
                    overage = produced_qty - qty
                    # Full bags only, overflow is accepted. Prefer fewer bags first.
                    cover_candidates.append((bag_qty, overage, -int(cones), cones, float(weight), produced_qty))
                    continue

                # If this lot cannot fully cover the target, consume full available bags from this combo.
                bag_qty = int(available_bags)
                if bag_qty <= 0:
                    continue
                produced_qty = float(bag_qty) * bag_weight
                partial_candidates.append((produced_qty, -bag_qty, -int(cones), cones, float(weight)))

        if cover_candidates:
            cover_candidates.sort()
            bag_qty, _overage, _neg_cones, cones, weight, produced_qty = cover_candidates[0]
        elif partial_candidates:
            partial_candidates.sort(reverse=True)
            produced_qty, _neg_bags, _neg_cones, cones, weight = partial_candidates[0]
            bag_qty = int(-_neg_bags)
        else:
            return None

        return {
            "bag_qty": int(bag_qty),
            "cone_qty": int(cones),
            "cone_weight": float(weight),
            "produced_qty": float(produced_qty),
        }

    def _thread_get_lot_history_order(self, move, source_location):
        controls = self.env["thread.lot.control"].search([
            ("product_id", "=", move.product_id.id),
        ])

        balances = {}
        source_id = source_location.id if source_location else False
        for control in controls:
            sign = 0
            if source_id:
                if control.dest_location_id and control.dest_location_id.id == source_id:
                    sign += 1
                if control.source_location_id and control.source_location_id.id == source_id:
                    sign -= 1
                if not control.source_location_id and not control.dest_location_id:
                    sign += 1
            else:
                if control.dest_location_id:
                    sign += 1
                if control.source_location_id:
                    sign -= 1
                if not control.source_location_id and not control.dest_location_id:
                    sign += 1

            if not sign:
                continue
            balances[control.lot_id.id] = balances.get(control.lot_id.id, 0) + sign * int(control.bag_count or 0)

        positive_lot_ids = [lot_id for lot_id, bags in sorted(balances.items(), key=lambda item: item[1], reverse=True) if bags > 0]
        return self.env["stock.lot"].browse(positive_lot_ids)

    def _thread_guess_lot_from_history(self, move, source_location):
        """Fallback lot inference when reserved move lines do not carry lot yet."""
        lots = self._thread_get_lot_history_order(move, source_location)
        return lots[:1]

    def _thread_get_lot_availability(self, move, lot, source_location, cache):
        cache_key = (lot.id, source_location.id if source_location else 0)
        if cache_key not in cache:
            cache[cache_key] = move._get_lot_combo_availability(lot, source_location=source_location)
        availability = cache[cache_key]

        if availability:
            return availability

        global_key = (lot.id, 0)
        if global_key not in cache:
            cache[global_key] = move._get_lot_combo_availability(lot, source_location=False)
        return cache[global_key]

    def _thread_fill_reserved_move_lines(self):
        move_line_model = self.env["stock.move.line"]
        has_legacy_bags = "bags" in move_line_model._fields
        has_legacy_cones = "cones" in move_line_model._fields

        for production in self:
            cache = {}
            moves = production.move_raw_ids.filtered(lambda mv: mv.product_id.is_thread)
            for move in moves:
                source_location = production.location_src_id or move.location_id
                lines = move.move_line_ids.filtered(lambda ml: ml.product_id.is_thread)
                if not lines and not source_location:
                    continue

                reserved_qty = float(sum(lines.mapped("quantity")) or 0.0)
                remaining_qty = reserved_qty or float(move.product_uom_qty or 0.0)
                lot_order = self._thread_get_lot_history_order(move, source_location)
                queue = list(lines)

                # If there are no reserved lines yet, create one placeholder to seed full-bag allocation.
                if not queue and remaining_qty > 0 and lot_order:
                    seed_vals = move._prepare_move_line_vals(quantity=0)
                    seed_vals["lot_id"] = lot_order[0].id
                    queue.append(move_line_model.create(seed_vals))

                while queue and remaining_qty > 0:
                    line = queue.pop(0)
                    line_source = line.location_id or source_location
                    preferred_lot = move._resolve_thread_lot_from_line(line) or self._thread_guess_lot_from_history(move, line_source)
                    qty_target = float(line.quantity or 0.0) or remaining_qty

                    candidate_lots = preferred_lot | lot_order
                    candidate_lots = candidate_lots.filtered(lambda lot: lot)
                    seen_lot_ids = set()

                    chosen_lot = False
                    chosen_combo = None
                    chosen_availability = None
                    for lot in candidate_lots:
                        if lot.id in seen_lot_ids:
                            continue
                        seen_lot_ids.add(lot.id)
                        availability = self._thread_get_lot_availability(move, lot, line_source, cache)
                        if not availability:
                            continue
                        combo = self._thread_pick_combo_for_quantity(availability, qty_target)
                        if not combo:
                            continue
                        chosen_lot = lot
                        chosen_combo = combo
                        chosen_availability = availability
                        # If this lot can already cover remaining demand with full bags, stop searching.
                        if float(combo.get("produced_qty", 0.0)) >= qty_target:
                            break

                    if not chosen_lot or not chosen_combo or not chosen_availability:
                        raise ValidationError(
                            "No thread combo availability was found to reserve %s kg for product %s."
                            % (move._fmt_weight(qty_target), move.product_id.display_name)
                        )

                    line_vals = {
                        "lot_id": chosen_lot.id,
                        "thread_bag_qty": chosen_combo["bag_qty"],
                        "thread_cone_qty": chosen_combo["cone_qty"],
                        "thread_cone_weight": chosen_combo["cone_weight"],
                    }
                    if has_legacy_bags:
                        line_vals["bags"] = chosen_combo["bag_qty"]
                    if has_legacy_cones:
                        line_vals["cones"] = chosen_combo["cone_qty"]
                    line.write(line_vals)

                    cone_bucket = chosen_availability.get(chosen_combo["cone_qty"], {})
                    current = int(cone_bucket.get(chosen_combo["cone_weight"], 0))
                    cone_bucket[chosen_combo["cone_weight"]] = max(current - chosen_combo["bag_qty"], 0)

                    produced_qty = float(chosen_combo.get("produced_qty") or line.quantity or 0.0)
                    remaining_qty = max(remaining_qty - produced_qty, 0.0)

                    # If demand is still pending and no draft line is available, create another line.
                    if remaining_qty > 0 and not queue:
                        extra_vals = move._prepare_move_line_vals(quantity=0)
                        extra_vals["lot_id"] = chosen_lot.id
                        queue.append(move_line_model.create(extra_vals))

    def action_assign(self):
        self._thread_align_raw_move_source_location()
        res = super().action_assign()
        self._thread_fill_reserved_move_lines()
        return res

    def action_confirm(self):
        res = super().action_confirm()
        self._thread_align_raw_move_source_location()
        return res
