import math

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError, UserError


class StockLocation(models.Model):
    _inherit = "stock.location"

    is_thread_main_location = fields.Boolean(string="Thread Main Warehouse")
    is_thread_production_location = fields.Boolean(string="Thread Production Warehouse")
    is_thread_second_quality_location = fields.Boolean(string="Thread Second Quality Warehouse")

    @api.constrains("is_thread_main_location", "company_id")
    def _check_unique_thread_main_location(self):
        for location in self.filtered("is_thread_main_location"):
            domain = [
                ("id", "!=", location.id),
                ("is_thread_main_location", "=", True),
                "|",
                ("company_id", "=", location.company_id.id),
                ("company_id", "=", False),
            ]
            if self.search_count(domain):
                raise ValidationError(
                    _("Solo puede existir una ubicacion marcada como almacen principal de hilo por compania.")
                )

    @api.constrains("is_thread_production_location", "company_id")
    def _check_unique_thread_production_location(self):
        for location in self.filtered("is_thread_production_location"):
            domain = [
                ("id", "!=", location.id),
                ("is_thread_production_location", "=", True),
                "|",
                ("company_id", "=", location.company_id.id),
                ("company_id", "=", False),
            ]
            if self.search_count(domain):
                raise ValidationError(
                    _("Solo puede existir una ubicacion marcada como almacen de produccion de hilo por compania.")
                )

    @api.constrains("is_thread_second_quality_location", "company_id")
    def _check_unique_thread_second_quality_location(self):
        for location in self.filtered("is_thread_second_quality_location"):
            domain = [
                ("id", "!=", location.id),
                ("is_thread_second_quality_location", "=", True),
                "|",
                ("company_id", "=", location.company_id.id),
                ("company_id", "=", False),
            ]
            if self.search_count(domain):
                raise ValidationError(
                    _("Solo puede existir una ubicacion marcada como almacen de hilo de segunda calidad por compania.")
                )


class StockMoveLine(models.Model):
    _inherit = "stock.move.line"

    thread_bag_qty = fields.Integer(string="Thread Bags", default=0)
    thread_cone_qty = fields.Integer(string="Cones per Bag", default=0)
    thread_total_cones = fields.Integer(string="Total Cones", compute="_compute_thread_totals", store=True)
    # Computed from quantity / (bags × cones) — the user enters total kg directly.
    thread_cone_weight = fields.Float(
        string="Cone Weight (kg)",
        compute="_compute_thread_cone_weight",
        store=True,
        digits=(16, 4),
    )

    @api.depends("thread_bag_qty", "thread_cone_qty")
    def _compute_thread_totals(self):
        for line in self:
            line.thread_total_cones = int((line.thread_bag_qty or 0) * (line.thread_cone_qty or 0))

    @api.depends("quantity", "thread_bag_qty", "thread_cone_qty")
    def _compute_thread_cone_weight(self):
        for line in self:
            bags = line.thread_bag_qty or 0
            cones = line.thread_cone_qty or 0
            qty = line.quantity or 0.0
            if bags > 0 and cones > 0 and qty > 0:
                line.thread_cone_weight = qty / (bags * cones)
            else:
                line.thread_cone_weight = 0.0

    @api.constrains("thread_bag_qty", "thread_cone_qty")
    def _check_thread_values(self):
        for line in self:
            if line.thread_bag_qty < 0 or line.thread_cone_qty < 0:
                raise ValidationError("Thread bags and cones cannot be negative.")

    def unlink(self):
        # Only block deletion from MO component detail dialogs.
        if self.env.context.get("active_mo_id"):
            blocked_lines = self.filtered(lambda l: l.move_id and l.move_id.raw_material_production_id and l.quantity > 0)
            if blocked_lines:
                raise UserError(_("In manufacturing component details, deleting lines is not allowed."))
        return super().unlink()

    @api.constrains(
        "move_id",
        "product_id",
        "quantity",
        "lot_id",
        "lot_name",
        "quant_id",
        "location_id",
        "thread_bag_qty",
        "thread_cone_qty",
        "thread_cone_weight",
    )
    def _check_thread_combo_on_detail_save(self):
        """Validate thread combo availability when saving detailed operations.

        This gives early feedback in the detailed operations popup instead of
        waiting until transfer validation.
        """
        if self.env.context.get("skip_thread_combo_validation"):
            return
        processed_keys = set()
        for line in self:
            move = line.move_id
            if not move or not line.product_id.is_thread:
                continue
            if move.picking_id and "Liquidacion Hilado" in (move.picking_id.origin or ""):
                continue

            movement_type = move._get_thread_movement_type()
            if movement_type not in ("out", "balance"):
                continue

            lot = move._resolve_thread_lot_from_line(line)
            if not lot:
                # Lot may still be incomplete while user is editing.
                continue

            source_location = line.location_id or move.location_id
            key = (move.id, lot.id, source_location.id if source_location else 0)
            if key in processed_keys:
                continue
            processed_keys.add(key)

            availability = move._get_lot_combo_availability(lot, source_location=source_location)

            sibling_lines = move.move_line_ids.filtered(
                lambda ml: ml.product_id.is_thread
                and ml.quantity > 0
                and (ml.location_id or move.location_id) == source_location
                and move._resolve_thread_lot_from_line(ml) == lot
            ).sorted("id")

            for sibling in sibling_lines:
                if sibling.thread_bag_qty <= 0 or sibling.thread_cone_qty <= 0 or sibling.thread_cone_weight <= 0:
                    continue
                move._consume_combo_or_raise(availability, sibling)


class StockMove(models.Model):
    _inherit = "stock.move"

    thread_control_generated = fields.Boolean(
        string="Thread Control Generated",
        default=False,
        copy=False,
        index=True,
    )

    @staticmethod
    def _thread_line_qty(line):
        qty = float(line.quantity or 0.0) if "quantity" in line._fields else 0.0
        if qty > 0:
            return qty
        if "qty_done" in line._fields:
            return float(line.qty_done or 0.0)
        return qty

    @staticmethod
    def _fmt_weight(value):
        text = f"{float(value or 0.0):.4f}".rstrip("0").rstrip(".")
        return text or "0"

    def _get_lot_combo_availability(self, lot, source_location=None):
        """Return available bag qty per (cones_per_bag, cone_weight) for a lot.

        If source_location is provided, availability is calculated for that
        specific location only.

        Structure:
            {
                10: {1.0: 20, 1.2: 5},
                20: {0.8: 12},
            }
        """
        controls = self.env["thread.lot.control"].search([("lot_id", "=", lot.id)])
        availability = {}
        for control in controls:
            for line in control.line_ids:
                cones = int(line.cone_qty or 0)
                weight = round(float(line.cone_weight or 0.0), 4)
                bags = int(line.bag_qty or 0)
                if cones <= 0 or weight <= 0 or bags <= 0:
                    continue

                sign = 0
                if source_location:
                    if control.source_location_id or control.dest_location_id:
                        if control.dest_location_id.id == source_location.id:
                            sign += 1
                        if control.source_location_id.id == source_location.id:
                            sign -= 1
                    else:
                        # Legacy controls created before location traceability are treated as available stock.
                        sign += 1
                else:
                    # Global lot availability (without source filter):
                    # +bags when entering a location, -bags when leaving a location.
                    if control.dest_location_id:
                        sign += 1
                    if control.source_location_id:
                        sign -= 1
                    if not control.source_location_id and not control.dest_location_id:
                        # Legacy controls without locations are considered positive stock snapshots.
                        sign += 1

                if not sign:
                    continue

                availability.setdefault(cones, {})
                availability[cones][weight] = availability[cones].get(weight, 0) + sign * bags
        return availability

    def _consume_combo_or_raise(self, availability, line):
        req_bags = int(line.thread_bag_qty or 0)
        req_cones = int(line.thread_cone_qty or 0)
        lot = self._resolve_thread_lot_from_line(line)
        lot_label = f" [{lot.name}]" if lot else ""

        if req_cones not in availability:
            raise ValidationError(f"No existen bolsas de {req_cones} conos en este lote{lot_label}.")

        cone_bucket = availability[req_cones]
        available_bags = sum(
            int(bags or 0)
            for bags in cone_bucket.values()
            if int(bags or 0) > 0
        )
        if available_bags <= 0:
            raise ValidationError(
                f"No hay disponibilidad de bolsas de {req_cones} conos en este lote{lot_label}."
            )
        if req_bags > available_bags:
            raise ValidationError(
                f"No hay bolsas suficientes de {req_cones} conos en este lote{lot_label}. "
                f"Disponible: {available_bags}."
            )

        remaining_bags = req_bags
        for weight in sorted(cone_bucket):
            if remaining_bags <= 0:
                break
            weight_bags = int(cone_bucket.get(weight, 0) or 0)
            if weight_bags <= 0:
                continue
            consumed_bags = min(weight_bags, remaining_bags)
            cone_bucket[weight] = weight_bags - consumed_bags
            remaining_bags -= consumed_bags

    def _resolve_thread_lot_from_line(self, line):
        """Resolve lot from a move line for all picking flows.

        Priority:
        1) lot_id (already selected/created)
        2) quant_id.lot_id (common in internal/outgoing operations)
        3) lot_name lookup (common in incoming before/after lot creation)
        """
        if line.lot_id:
            return line.lot_id
        if line.quant_id and line.quant_id.lot_id:
            return line.quant_id.lot_id
        if line.lot_name:
            return self.env["stock.lot"].search([
                ("name", "=", line.lot_name),
                ("product_id", "=", line.product_id.id),
                "|",
                ("company_id", "=", line.company_id.id),
                ("company_id", "=", False),
            ], limit=1)
        return self.env["stock.lot"]

    thread_is_thread = fields.Boolean(string="Is Thread", related="product_id.is_thread", store=True)

    def _get_thread_movement_type(self):
        self.ensure_one()
        picking = self.picking_id
        if not picking:
            return False

        # Los traslados creados por el wizard de liquidacion siempre deben
        # registrarse como segunda calidad para los acumulados del lote.
        if picking.thread_liquidation_production_id:
            return "balance"

        src = picking.location_id
        dst = picking.location_dest_id

        # Any incoming transfer of thread product is an inventory entry for the lot control.
        if picking.picking_type_code == "incoming":
            return "in"

        if picking.picking_type_code == "outgoing":
            return "out"

        if picking.picking_type_code != "internal":
            return False

        if src.is_thread_main_location and dst.is_thread_production_location:
            return "out"
        if src.is_thread_production_location and dst.is_thread_second_quality_location:
            return "balance"
        if dst.is_thread_second_quality_location:
            return "balance"
        if dst.is_thread_main_location:
            return "in"

        # Fallback to keep traceability even if location flags are not configured yet.
        return "out"

    def _check_thread_transfer_data(self):
        if self.env.context.get("skip_thread_combo_validation"):
            return
        lot_availability_cache = {}
        for move in self:
            if move.picking_id and "Liquidacion Hilado" in (move.picking_id.origin or ""):
                continue
            movement_type = move._get_thread_movement_type()
            if not movement_type or not move.product_id.is_thread:
                continue

            detailed_lines = move.move_line_ids.filtered(lambda ml: move._thread_line_qty(ml) > 0)
            if detailed_lines:
                line_with_lot = detailed_lines.filtered(
                    lambda ml: ml.lot_id or ml.lot_name or (ml.quant_id and ml.quant_id.lot_id)
                )
                if not line_with_lot:
                    raise ValidationError("Thread move requires lot in detailed operations.")

                for line in line_with_lot:
                    if line.thread_bag_qty <= 0:
                        raise ValidationError("Thread move line requires Bags > 0.")
                    if line.thread_cone_qty <= 0:
                        raise ValidationError("Thread move line requires Cones per Bag > 0.")
                    if line.thread_cone_weight <= 0:
                        raise ValidationError("Thread move line requires Cone Weight > 0.")

                    # Restricciones de integridad para despachos/liquidaciones:
                    # solo se puede mover combinaciones que existan en el lote.
                    if movement_type in ("out", "balance"):
                        lot = move._resolve_thread_lot_from_line(line)
                        if not lot:
                            raise ValidationError("Thread move requires a valid lot in detailed operations.")
                        source_location = line.location_id or move.location_id
                        cache_key = (lot.id, source_location.id if source_location else 0)
                        availability = lot_availability_cache.setdefault(
                            cache_key,
                            move._get_lot_combo_availability(lot, source_location=source_location),
                        )
                        move._consume_combo_or_raise(availability, line)
                continue
            raise ValidationError("Thread move requires detailed operations with lot, bags, cones and cone weight.")

    def _create_thread_controls_from_move(self):
        if self.env.context.get("skip_thread_control_creation"):
            return
        control_model = self.env["thread.lot.control"]
        for move in self:
            if move.thread_control_generated:
                continue

            movement_type = move._get_thread_movement_type()
            if not movement_type or not move.product_id.is_thread:
                continue

            control_date = fields.Date.context_today(self)
            if move.picking_id and move.picking_id.date_done:
                control_date = fields.Date.to_date(move.picking_id.date_done)

            lines = move.move_line_ids.filtered(lambda ml: move._thread_line_qty(ml) > 0)
            if lines:
                by_lot = {}
                for line in lines:
                    lot = move._resolve_thread_lot_from_line(line)
                    if not lot:
                        continue
                    source_location = line.location_id or move.location_id
                    dest_location = line.location_dest_id or move.location_dest_id
                    key = (lot.id, source_location.id if source_location else 0, dest_location.id if dest_location else 0)
                    by_lot.setdefault(key, []).append(line)

                if not by_lot:
                    continue

                for (lot_id, source_location_id, dest_location_id), lot_lines in by_lot.items():
                    command_lines = [
                        (0, 0, {
                            "bag_qty": line.thread_bag_qty,
                            "cone_qty": line.thread_cone_qty,
                            "total_weight": float(line.quantity or 0.0),
                        })
                        for line in lot_lines
                    ]
                    control_model.create({
                        "date": control_date,
                        "movement_type": movement_type,
                        "lot_id": lot_id,
                        "source_location_id": source_location_id or False,
                        "dest_location_id": dest_location_id or False,
                        "note": f"Auto-generated from transfer {move.picking_id.name or move.reference or ''}",
                        "line_ids": command_lines,
                    })

                move.thread_control_generated = True

    def _action_done(self, cancel_backorder=False):
        self._check_thread_transfer_data()
        done_moves = super()._action_done(cancel_backorder=cancel_backorder)
        done_moves.with_context(**self.env.context)._create_thread_controls_from_move()
        return done_moves

    def action_open_packing_import_wizard(self):
        self.ensure_one()
        return {
            "name": _("Importar Packing List de Hilo"),
            "type": "ir.actions.act_window",
            "res_model": "stock.move.import.packing.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_move_id": self.id,
            },
        }


class StockPicking(models.Model):
    _inherit = "stock.picking"

    thread_liquidation_production_id = fields.Many2one(
        "mrp.production",
        string="MO Liquidacion Hilado",
        copy=False,
        index=True,
    )
    is_thread_liquidation = fields.Boolean(
        string="Es Liquidacion de Hilo",
        compute="_compute_is_thread_liquidation",
        store=True,
    )

    @api.depends("thread_liquidation_production_id")
    def _compute_is_thread_liquidation(self):
        for picking in self:
            picking.is_thread_liquidation = bool(picking.thread_liquidation_production_id)

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
                    cover_candidates.append((bag_qty, overage, -int(cones), cones, float(weight), produced_qty))
                    continue

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

        for picking in self:
            cache = {}
            moves = picking.move_ids.filtered(lambda mv: mv.product_id.is_thread and mv.state not in ("done", "cancel"))
            for move in moves:
                source_location = move.location_id or picking.location_id
                lines = move.move_line_ids.filtered(lambda ml: ml.product_id.is_thread and ml.state not in ("done", "cancel"))
                if not lines and not source_location:
                    continue

                reserved_qty = float(sum(lines.mapped("quantity")) or 0.0)
                remaining_qty = reserved_qty or float(move.product_uom_qty or 0.0)
                lot_order = self._thread_get_lot_history_order(move, source_location)
                queue = list(lines)

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
                        if float(combo.get("produced_qty", 0.0)) >= qty_target:
                            break

                    if not chosen_lot or not chosen_combo or not chosen_availability:
                        raise ValidationError(
                            _("No thread combo availability was found to reserve %(qty)s kg for product %(product)s.",
                              qty=self.env["stock.move"]._fmt_weight(qty_target),
                              product=move.product_id.display_name)
                        )

                    line_vals = {
                        "lot_id": chosen_lot.id,
                        "quantity": float(chosen_combo.get("produced_qty") or qty_target or 0.0),
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

                    produced_qty = float(chosen_combo.get("produced_qty") or qty_target or line.quantity or 0.0)
                    remaining_qty = max(remaining_qty - produced_qty, 0.0)

                    if remaining_qty > 0 and not queue:
                        extra_vals = move._prepare_move_line_vals(quantity=remaining_qty)
                        extra_vals["lot_id"] = chosen_lot.id
                        queue.append(move_line_model.create(extra_vals))

    def action_open_picking_packing_import_wizard(self):
        self.ensure_one()
        return {
            "name": _("Importar Packing List de Hilo"),
            "type": "ir.actions.act_window",
            "res_model": "stock.picking.import.packing.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_picking_id": self.id},
        }

    def action_assign(self):
        res = super().action_assign()
        self._thread_fill_reserved_move_lines()
        # No validar combos estrictamente en reserva: en confirmacion de MO puede
        # haber ajustes de combinacion pendientes. La validacion fuerte se mantiene
        # en _action_done del movimiento.
        return res
