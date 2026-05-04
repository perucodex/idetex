from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class ThreadSecondQualityWizard(models.TransientModel):
    _name = "thread.second.quality.wizard"
    _description = "Thread Second Quality Wizard"

    production_id = fields.Many2one("mrp.production", string="Manufacturing Order", required=True, readonly=True)
    source_location_id = fields.Many2one("stock.location", string="Ubicacion Produccion", readonly=True)
    destination_location_id = fields.Many2one("stock.location", string="Ubicacion Destino")
    main_location_id = fields.Many2one("stock.location", string="Ubicacion Principal", readonly=True)
    second_location_id = fields.Many2one("stock.location", string="Ubicacion Segunda", readonly=True)
    line_ids = fields.One2many("thread.second.quality.wizard.line", "wizard_id", string="Thread Lots")

    @api.model
    def _infer_source_location_from_mo_pickings(self, production):
        """Inferir ubicacion de produccion desde transferencias hechas de la MO."""
        done_thread_moves = production.picking_ids.filtered(lambda p: p.state == "done").move_ids.filtered(
            lambda m: m.product_id.is_thread and m.location_dest_id and m.location_dest_id.usage == "internal"
        )
        candidate_locs = done_thread_moves.mapped("location_dest_id")
        return candidate_locs[:1] if len(candidate_locs) == 1 else self.env["stock.location"]

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        production_id = self.env.context.get("default_production_id")
        if not production_id:
            return res

        production = self.env["mrp.production"].browse(production_id).exists()
        if not production:
            return res

        # Se resuelven ubicaciones configuradas para limitar destinos permitidos.
        source_locations = self.env["stock.location"].search([
            ("is_thread_production_location", "=", True),
            "|", ("company_id", "=", production.company_id.id), ("company_id", "=", False),
        ])
        main_locations = self.env["stock.location"].search([
            ("is_thread_main_location", "=", True),
            "|", ("company_id", "=", production.company_id.id), ("company_id", "=", False),
        ])
        second_locations = self.env["stock.location"].search([
            ("is_thread_second_quality_location", "=", True),
            "|", ("company_id", "=", production.company_id.id), ("company_id", "=", False),
        ])

        source_location = source_locations[:1] if len(source_locations) == 1 else self._infer_source_location_from_mo_pickings(production)
        main_location = main_locations[:1] if len(main_locations) == 1 else self.env["stock.location"]
        second_location = second_locations[:1] if len(second_locations) == 1 else self.env["stock.location"]

        res["production_id"] = production.id
        if source_location:
            res["source_location_id"] = source_location.id
        if main_location:
            res["main_location_id"] = main_location.id
        if second_location:
            res["second_location_id"] = second_location.id
            res["destination_location_id"] = second_location.id

        consumed_map, received_map, liquidated_map = production._thread_get_liquidation_maps(
            source_location=source_location
        )

        availability_balance_map = {}
        combo_default_map = {}
        source_loc = self.env["stock.location"].browse(res["source_location_id"]) if res.get("source_location_id") else self.env["stock.location"]
        move_model = self.env["stock.move"]
        lot_model = self.env["stock.lot"]
        candidate_keys = set(consumed_map.keys()) | set(received_map.keys()) | set(liquidated_map.keys())
        for product_id, lot_id in candidate_keys:
            lot = lot_model.browse(lot_id)
            availability = move_model._get_lot_combo_availability(lot, source_location=source_loc) if source_loc else {}
            balance_qty = 0.0
            positive_combos = []
            for cones, weight_map in availability.items():
                for weight, bags in weight_map.items():
                    bag_qty = int(bags or 0)
                    if bag_qty <= 0:
                        continue
                    balance_qty += float(bag_qty) * float(cones) * float(weight)
                    positive_combos.append((bag_qty, int(cones), float(weight)))
            availability_balance_map[(product_id, lot_id)] = balance_qty
            if len(positive_combos) == 1:
                combo_default_map[(product_id, lot_id)] = positive_combos[0]

        line_commands = []
        lot_keys = set(consumed_map.keys()) | set(received_map.keys()) | set(availability_balance_map.keys())
        for (product_id, lot_id) in sorted(lot_keys):
            consumed_qty = consumed_map.get((product_id, lot_id), 0.0)
            received_qty = received_map.get((product_id, lot_id), 0.0)
            liquidated_qty = liquidated_map.get((product_id, lot_id), 0.0)
            availability_balance = max(availability_balance_map.get((product_id, lot_id), 0.0), 0.0)
            if not received_qty and (consumed_qty > 0 or availability_balance > 0):
                # Si no hubo picking MO->produccion, se reconstruye recibido para referencia visual.
                received_qty = consumed_qty + availability_balance

            # Regla principal: saldo pendiente = recibido - consumido - ya liquidado.
            balance_qty = max(received_qty - consumed_qty - liquidated_qty, 0.0)

            bag_qty, cone_qty, transfer_qty = 0, 0, 0.0
            combo_default = combo_default_map.get((product_id, lot_id))
            if combo_default and balance_qty > 0:
                _avail_bags, combo_cones, combo_weight = combo_default
                cone_qty = int(combo_cones)

                # Se precarga sobre el saldo de la MO (no sobre todas las bolsas disponibles del lote).
                unit_bag_weight = float(combo_cones) * float(combo_weight)
                if unit_bag_weight > 0:
                    approx_bags = balance_qty / unit_bag_weight
                    rounded_bags = int(round(approx_bags))

                    if rounded_bags > 0 and abs((rounded_bags * unit_bag_weight) - balance_qty) <= 1e-6:
                        # Caso exacto por combinacion de lote.
                        bag_qty = rounded_bags
                        transfer_qty = round(float(rounded_bags) * float(cone_qty) * float(combo_weight), 3)
                    else:
                        # Caso no exacto: 1 bolsa, total kg = saldo.
                        bag_qty = 1
                        transfer_qty = round(balance_qty, 3)

            line_commands.append((0, 0, {
                "product_id": product_id,
                "lot_id": lot_id,
                "received_qty": received_qty,
                "consumed_qty": consumed_qty,
                "liquidated_qty": liquidated_qty,
                "balance_qty": balance_qty,
                "bag_qty": bag_qty,
                "cone_qty": cone_qty,
                "transfer_qty": transfer_qty,
            }))
        res["line_ids"] = line_commands
        return res

    def _get_unique_thread_locations(self):
        self.ensure_one()
        company = self.production_id.company_id
        domain_company = ["|", ("company_id", "=", company.id), ("company_id", "=", False)]

        production_locations = self.env["stock.location"].search(
            [("is_thread_production_location", "=", True)] + domain_company
        )
        if len(production_locations) != 1:
            raise UserError(_(
                "Debe existir exactamente una ubicacion de produccion de hilo para la compania."
            ))

        main_locations = self.env["stock.location"].search(
            [("is_thread_main_location", "=", True)] + domain_company
        )
        if len(main_locations) != 1:
            raise UserError(_(
                "Debe existir exactamente una ubicacion principal de hilo para la compania."
            ))

        second_locations = self.env["stock.location"].search(
            [("is_thread_second_quality_location", "=", True)] + domain_company
        )
        if len(second_locations) != 1:
            raise UserError(_(
                "Debe existir exactamente una ubicacion de segunda calidad de hilo para la compania."
            ))

        return production_locations[:1], main_locations[:1], second_locations[:1]

    def _get_internal_picking_type(self):
        self.ensure_one()
        company = self.production_id.company_id
        picking_type = self.env["stock.picking.type"].search([
            ("code", "=", "internal"),
            ("warehouse_id.company_id", "=", company.id),
        ], limit=1)
        if not picking_type:
            raise UserError(_("No se encontro un tipo de operacion interna para la compania."))
        return picking_type

    def action_create_second_quality_transfer(self):
        self.ensure_one()
        incomplete_lines = self.line_ids.filtered(
            lambda l: l.transfer_qty > 0 and (not l.product_id or not l.lot_id)
        )
        if incomplete_lines:
            raise UserError(_(
                "Hay lineas incompletas en el asistente (sin producto o lote). "
                "Cierre y vuelva a abrir la ventana de liquidacion."
            ))

        transfer_lines = self.line_ids.filtered(lambda l: l.product_id and l.lot_id and l.transfer_qty > 0)
        if not transfer_lines:
            raise UserError(_("Debe indicar al menos una linea con cantidad a transferir."))

        source_location, main_location, second_location = self._get_unique_thread_locations()
        allowed_dest_ids = {main_location.id, second_location.id}
        if not self.destination_location_id:
            raise ValidationError(_("Debe seleccionar una ubicacion destino."))
        if self.destination_location_id.id not in allowed_dest_ids:
            raise ValidationError(_("La ubicacion destino debe ser Principal o Segunda Calidad."))

        dest_location = self.destination_location_id
        picking_type = self._get_internal_picking_type()
        move_model = self.env["stock.move"]

        for line in transfer_lines:
            if not line.product_id:
                raise ValidationError(_("Falta Producto en una linea del asistente de liquidacion."))
            if not line.lot_id:
                raise ValidationError(_("Falta Lote en una linea del asistente de liquidacion."))
            if line.bag_qty <= 0 or line.cone_qty <= 0 or line.transfer_qty <= 0:
                raise ValidationError(_(
                    "Debe ingresar Bolsas, Conos por Bolsa y Kg a Enviar mayores que cero para %(lot)s.",
                    lot=line.lot_id.name,
                ))

            # El peso por cono en liquidacion no puede superar el peso original del lote.
            availability = move_model._get_lot_combo_availability(line.lot_id, source_location=source_location)
            original_weights = [
                float(weight)
                for _cones, weight_map in availability.items()
                for weight, bags in weight_map.items()
                if int(bags or 0) > 0 and float(weight or 0.0) > 0
            ]
            if original_weights:
                max_original_weight = max(original_weights)
                if float(line.cone_weight or 0.0) > max_original_weight:
                    raise ValidationError(_(
                        "El Peso por Cono (%(input)s) no puede ser mayor al peso original del lote (%(max)s) para %(lot)s.",
                        input=round(float(line.cone_weight or 0.0), 4),
                        max=round(float(max_original_weight), 4),
                        lot=line.lot_id.name,
                    ))

            if line.transfer_qty > line.balance_qty:
                raise ValidationError(_(
                    "La cantidad a transferir no puede ser mayor que el saldo para el lote %(lot)s.",
                    lot=line.lot_id.name,
                ))

        action = False
        created_pickings = self.env["stock.picking"]
        picking = self.env["stock.picking"].create({
            "picking_type_id": picking_type.id,
            "location_id": source_location.id,
            "location_dest_id": dest_location.id,
            "origin": "%s - Liquidacion Hilado" % self.production_id.name,
            "thread_liquidation_production_id": self.production_id.id,
            "company_id": self.production_id.company_id.id,
        })

        for line in transfer_lines:
            qty = line.transfer_qty
            if qty <= 0:
                continue

            move = move_model.create({
                "description_picking": "%s - %s" % (line.product_id.display_name, line.lot_id.name),
                "picking_id": picking.id,
                "product_id": line.product_id.id,
                "product_uom_qty": qty,
                "product_uom": line.product_id.uom_id.id,
                "location_id": source_location.id,
                "location_dest_id": dest_location.id,
                "company_id": self.production_id.company_id.id,
            })

            vals = move._prepare_move_line_vals(quantity=qty)
            vals.update({
                "lot_id": line.lot_id.id,
                "quantity": qty,
                "thread_bag_qty": line.bag_qty,
                "thread_cone_qty": line.cone_qty,
                "location_id": source_location.id,
                "location_dest_id": dest_location.id,
            })
            if "picked" in self.env["stock.move.line"]._fields:
                vals["picked"] = True
            self.env["stock.move.line"].with_context(
                skip_thread_combo_validation=True,
            ).create(vals)

        if not picking.move_ids:
            # Evita error core: "Nothing to check the availability for."
            picking.unlink()
        else:
            picking.action_confirm()
            moves_todo = picking.move_ids.filtered(
                lambda m: m.state in ("draft", "waiting", "confirmed", "partially_available", "assigned")
            )
            if moves_todo:
                moves_todo.with_context(
                    skip_mo_check=True,
                    skip_thread_combo_validation=True,
                )._action_done(cancel_backorder=False)

            # Si no hay moves por procesar puede ser porque ya quedaron en done por flujo previo.
            if not picking.move_ids.filtered(lambda m: m.state == "done"):
                picking.unlink()
            else:
                # Fallback defensivo: asegura trazabilidad en thread.lot.control
                # aunque el flujo del core no haya disparado _action_done esperado.
                picking.move_ids.filtered(
                    lambda m: m.state == "done" and m.product_id.is_thread
                )._create_thread_controls_from_move()
                created_pickings |= picking

        if created_pickings:
            first_picking = created_pickings[:1]
            action = {
                "type": "ir.actions.act_window",
                "res_model": "stock.picking",
                "view_mode": "form",
                "res_id": first_picking.id,
                "target": "current",
            }
        else:
            raise UserError(_(
                "No se generaron movimientos para liquidar. Revise cantidades y destinos."
            ))

        # Refresca cache de liquidaciones para el smart button dedicado.
        self.production_id.invalidate_recordset(["thread_liquidation_picking_ids", "thread_liquidation_count"])
        self.production_id._compute_thread_liquidation_count()

        return action or {"type": "ir.actions.act_window_close"}


class ThreadSecondQualityWizardLine(models.TransientModel):
    _name = "thread.second.quality.wizard.line"
    _description = "Thread Second Quality Wizard Line"

    wizard_id = fields.Many2one("thread.second.quality.wizard", required=True, ondelete="cascade")
    # En listas editables, Odoo puede generar filas transitorias sin claves requeridas
    # durante la edicion; la validacion funcional se hace al liquidar.
    product_id = fields.Many2one("product.product", string="Producto", readonly=True)
    lot_id = fields.Many2one("stock.lot", string="Lote", readonly=True)

    received_qty = fields.Float(string="Kg Recibidos", readonly=True)
    consumed_qty = fields.Float(string="Kg Consumidos", readonly=True)
    liquidated_qty = fields.Float(string="Kg Liquidados", readonly=True)
    balance_qty = fields.Float(string="Saldo (Kg)", readonly=True)
    bag_qty = fields.Integer(string="Bolsas")
    cone_qty = fields.Integer(string="Conos por Bolsa")
    transfer_qty = fields.Float(string="Kg a Enviar", default=0.0, digits=(16, 3))
    # Calculado a partir de Kg a Enviar / (bolsas × conos) — solo lectura.
    cone_weight = fields.Float(
        string="Peso por Cono (kg)",
        compute="_compute_cone_weight",
        digits=(16, 4),
    )

    @api.depends("transfer_qty", "bag_qty", "cone_qty")
    def _compute_cone_weight(self):
        for line in self:
            bags = line.bag_qty or 0
            cones = line.cone_qty or 0
            qty = line.transfer_qty or 0.0
            if bags > 0 and cones > 0 and qty > 0:
                line.cone_weight = qty / (bags * cones)
            else:
                line.cone_weight = 0.0

    @api.constrains("transfer_qty", "bag_qty", "cone_qty")
    def _check_transfer_qty(self):
        for line in self:
            # Ignorar filas transitorias incompletas del list editable.
            if not line.product_id or not line.lot_id:
                continue
            if line.bag_qty < 0 or line.cone_qty < 0:
                raise ValidationError(_("Bolsas y Conos por Bolsa no pueden ser negativos."))
            if line.transfer_qty < 0:
                raise ValidationError(_("La cantidad a enviar no puede ser negativa."))
            if line.transfer_qty > line.balance_qty:
                raise ValidationError(_(
                    "Los Kg a enviar (%(send)s) no pueden ser mayores al saldo (%(balance)s) para el lote %(lot)s.",
                    send=round(line.transfer_qty, 4),
                    balance=round(line.balance_qty, 4),
                    lot=line.lot_id.display_name,
                ))
