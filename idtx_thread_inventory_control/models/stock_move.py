from odoo import _, api, fields, models
from odoo.exceptions import UserError


class StockPicking(models.Model):
    _inherit = "stock.picking"

    thread_received_bag_ids = fields.One2many(
        "thread.bag", "receipt_picking_id", string="Bolsas Recibidas",
    )
    thread_received_bag_count = fields.Integer(
        compute="_compute_thread_received_bag_count", string="N° Bolsas Recibidas",
    )
    thread_liquidation_production_id = fields.Many2one(
        "mrp.production", string="Orden de Producción (Liquidación)", index=True,
    )

    def _compute_thread_received_bag_count(self):
        for picking in self:
            picking.thread_received_bag_count = len(picking.thread_received_bag_ids)

    def action_view_thread_received_bags(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Bolsas Recibidas"),
            "res_model": "thread.bag",
            "view_mode": "list,form",
            "domain": [("receipt_picking_id", "=", self.id)],
            "context": {'search_default_available': True, 'search_default_group_lot': True},
        }


class StockMove(models.Model):
    _inherit = "stock.move"

    thread_is_thread = fields.Boolean(
        string="Es Hilo", related="product_id.is_thread", store=True,
    )
    thread_bag_ids = fields.Many2many(
        "thread.bag", "thread_bag_stock_move_rel", "move_id", "bag_id",
        string="Bolsas Seleccionadas", copy=False,
        help="Bolsas de hilo elegidas para mover/consumir en este movimiento.",
    )
    thread_selected_net = fields.Float(
        string="Kg Seleccionados", compute="_compute_thread_selected",
        digits=(16, 3), store=True,
    )
    thread_selected_bag_count = fields.Integer(
        string="Bolsas Seleccionadas (n)", compute="_compute_thread_selected", store=True,
    )
    thread_control_generated = fields.Boolean(string="Control Generado", default=False)
    thread_pending_bag_data = fields.Json(
        string="Packing de hilo pendiente", copy=False,
        help="Datos por bolsa del packing importado en una RECEPCIÓN, a la espera "
             "de validar: recién al validar se crean los lotes y las bolsas.",
    )

    @api.depends("thread_bag_ids", "thread_bag_ids.net_weight")
    def _compute_thread_selected(self):
        for move in self:
            move.thread_selected_net = sum(move.thread_bag_ids.mapped("net_weight"))
            move.thread_selected_bag_count = len(move.thread_bag_ids)

    def _action_assign(self, force_qty=False):
        """Bypass de la reserva nativa para productos de hilo.

        Al confirmar (o pulsar 'Comprobar disponibilidad') el core auto-reserva y
        rellena el detalle con la demanda + un lote. Para hilo NO queremos eso: el
        detalle se arma SOLO al elegir/escanear bolsas. Por eso saltamos la reserva
        de los movimientos de hilo (no se crean líneas automáticas)."""
        non_thread = self.filtered(lambda m: not m.product_id.is_thread)
        if non_thread:
            return super(StockMove, non_thread)._action_assign(force_qty=force_qty)
        return None

    # ------------------------------------------------------------------
    # Selección de bolsas
    # ------------------------------------------------------------------
    def action_open_thread_bag_selector(self):
        self.ensure_one()
        if not self.product_id.is_thread:
            raise UserError(_("Este movimiento no es de un producto de hilo."))
        # El wizard se crea en el SERVIDOR (no vía defaults) para poder
        # rehidratar el packing persistido en el movimiento al reabrirlo.
        wiz = self.env["thread.bag.consume.wizard"]._create_for_move(self)
        return {
            "type": "ir.actions.act_window",
            "name": _("Elegir bolsas de hilo"),
            "res_model": "thread.bag.consume.wizard",
            "res_id": wiz.id,
            "view_mode": "form",
            "target": "new",
        }

    def _thread_apply_bag_selection(self, bags):
        """Fija las líneas del movimiento a partir de las bolsas elegidas.

        Una línea por lote, cantidad = suma de pesos netos de las bolsas de ese
        lote. La demanda se ajusta al total elegido para que el core no parta el
        excedente. Las bolsas quedan reservadas y enlazadas al movimiento.
        """
        self.ensure_one()
        MoveLine = self.env["stock.move.line"]
        # Liberar bolsas previamente seleccionadas que ya no están.
        old = self.thread_bag_ids - bags
        if old:
            old.action_reset_available()
        # Quitar líneas pendientes anteriores.
        self.move_line_ids.filtered(lambda l: l.state not in ("done", "cancel")).unlink()

        # Alinear el origen del movimiento a la ubicación de las bolsas (si todas
        # están en una sola): así la OF/transferencia consume desde donde el hilo
        # realmente está y el quant correcto se decrementa.
        locations = bags.mapped("location_id")
        if len(locations) == 1 and locations and self.location_id != locations:
            self.with_context(no_procurement=True).location_id = locations.id

        # Agrupar por (lote, ubicación física de la bolsa): la línea debe partir
        # de donde están realmente las bolsas para decrementar el quant correcto.
        by_key = {}
        for bag in bags:
            key = (bag.lot_id, bag.location_id)
            by_key.setdefault(key, self.env["thread.bag"])
            by_key[key] |= bag

        for (lot, location), grp_bags in by_key.items():
            line = MoveLine.create({
                "move_id": self.id,
                "product_id": self.product_id.id,
                "product_uom_id": self.product_uom.id,
                "lot_id": lot.id,
                "quantity": sum(grp_bags.mapped("net_weight")),
                # picked=True: la cantidad es la real de las bolsas elegidas. Así
                # la demanda original NO se toca y el core no parte el excedente
                # ni recrea líneas auto-reservadas (descarta las no "picked").
                "picked": True,
                # origen = ubicación real de la bolsa (si la tiene), si no la del move.
                "location_id": (location or self.location_id).id,
                "location_dest_id": self.location_dest_id.id,
                "company_id": self.company_id.id,
            })
            grp_bags.write({
                "state": "reserved",
                "consumed_move_line_id": line.id,
            })

        self.thread_bag_ids = [(6, 0, bags.ids)]
        # NOTA: la demanda (product_uom_qty) se deja intacta a propósito. Lo
        # elegido (peso neto real de las bolsas) puede superar la demanda: es
        # sobre-entrega; el saldo se liquida después.

    def _thread_apply_reception_lines(self, lines):
        """Arma el detalle de una RECEPCIÓN de hilo a partir de las líneas del
        packing importado (transitorias), SIN crear lotes ni bolsas todavía.

        - Crea una línea de detalle por LOTE con la cantidad = suma de pesos netos,
          poniendo el lote como TEXTO (`lot_name`); Odoo creará el lote al validar
          (tipo de operación con `use_create_lots`).
        - Guarda los datos por-bolsa en `move.thread_pending_bag_data`; recién al
          VALIDAR se crean las `thread.bag` (ver `_action_done`).
        - NO setea `thread_bag_ids` (para que al validar las bolsas no se marquen
          consumidas). La demanda (`product_uom_qty`) queda intacta (= lo pedido).
        """
        self.ensure_one()
        MoveLine = self.env["stock.move.line"]
        product = self.product_id
        tracked = product.tracking in ("lot", "serial")

        # Datos por bolsa (para crear las bolsas al validar) + agregado por lote.
        data = []
        by_lot = {}
        for ln in lines:
            data.append({
                "name": ln.name, "lot_name": ln.lot_name, "cone_qty": ln.cone_qty,
                "net_weight": ln.net_weight, "gross_weight": ln.gross_weight,
                "tare": ln.tare, "cone_color": ln.cone_color,
                "packaging_type": ln.packaging_type, "yarn_color": ln.yarn_color,
            })
            key = ln.lot_name if tracked else False
            by_lot[key] = by_lot.get(key, 0.0) + ln.net_weight

        # Reconstruir las líneas de detalle (una por lote).
        self.move_line_ids.filtered(lambda l: l.state not in ("done", "cancel")).unlink()
        for lot_name, qty in by_lot.items():
            MoveLine.create({
                "move_id": self.id,
                "product_id": product.id,
                "product_uom_id": self.product_uom.id,
                "lot_name": lot_name if tracked else False,
                "quantity": qty,
                "picked": True,
                "location_id": self.location_id.id,
                "location_dest_id": self.location_dest_id.id,
                "company_id": self.company_id.id,
            })

        self.thread_pending_bag_data = data or False

    def _thread_create_bags_from_pending(self):
        """Crea las `thread.bag` del packing pendiente tras VALIDAR la recepción.

        Se llama desde `_action_done` (ya con los lotes creados por Odoo a partir
        de `lot_name`). Toma el lote de las líneas ya hechas (`move_line_ids`), o lo
        busca/crea como respaldo, y da de alta una bolsa por fila guardada.
        Idempotente: omite correlativos que ya existan.
        """
        self.ensure_one()
        data = self.thread_pending_bag_data or []
        if not data:
            return
        Bag = self.env["thread.bag"]
        company = self.company_id
        dest = self.location_dest_id
        # Lote por nombre: Odoo ya lo asignó a las líneas al validar.
        lot_by_name = {
            ml.lot_id.name: ml.lot_id for ml in self.move_line_ids if ml.lot_id
        }
        existing = set(Bag.with_context(active_test=False).search([
            ("name", "in", [r["name"] for r in data]),
            ("company_id", "=", company.id),
        ]).mapped("name"))
        vals = []
        for r in data:
            if r["name"] in existing:
                continue
            lot = lot_by_name.get(r["lot_name"]) or Bag._get_or_create_lot(
                self.product_id, r["lot_name"], company)
            vals.append({
                "name": r["name"],
                "product_id": self.product_id.id,
                "lot_id": lot.id,
                "location_id": dest.id,
                "cone_qty": r.get("cone_qty") or 1,
                "gross_weight": r.get("gross_weight") or 0.0,
                "tare": r.get("tare") or 0.0,
                "net_weight": r.get("net_weight") or 0.0,
                "cone_color": r.get("cone_color") or False,
                "packaging_type": r.get("packaging_type") or False,
                "yarn_color": r.get("yarn_color") or False,
                "company_id": company.id,
                "receipt_picking_id": self.picking_id.id,
                "state": "available",
            })
        if vals:
            Bag.create(vals)
        self.thread_pending_bag_data = False

    # ------------------------------------------------------------------
    # Validación: consumir / reubicar bolsas
    # ------------------------------------------------------------------
    def _action_done(self, cancel_backorder=False):
        done_moves = super()._action_done(cancel_backorder=cancel_backorder)
        for move in done_moves:
            # Recepción de hilo: crear ahora los lotes/bolsas del packing pendiente
            # (los lotes ya los creó el core a partir de lot_name).
            if move.thread_pending_bag_data:
                move._thread_create_bags_from_pending()
            bags = move.thread_bag_ids
            if not bags:
                continue
            dest = move.location_dest_id
            if move.raw_material_production_id:
                # Consumo en producción.
                bags.action_mark_consumed(
                    production=move.raw_material_production_id, location=dest)
            elif move.location_id.usage == "internal" and dest.usage == "internal":
                # Transferencia interna: la bolsa se reubica y sigue disponible.
                # (scrap/ajustes usan usage 'inventory' -> caen en el else.)
                bags.write({"state": "available", "location_id": dest.id,
                            "consumed_move_line_id": False})
            else:
                # Salida (cliente / scrap / etc.).
                bags.action_mark_consumed(location=dest)
        return done_moves


class StockMoveLine(models.Model):
    _inherit = "stock.move.line"

    thread_bag_qty = fields.Integer(string="Bolsas", default=0)
    thread_cone_qty = fields.Integer(string="Conos/Bolsa", default=0)
    thread_cone_weight = fields.Float(string="Peso Cono (kg)", digits=(12, 4), default=0.0)
    thread_total_cones = fields.Integer(
        compute="_compute_thread_totals", string="Total Conos",
    )

    def _compute_thread_totals(self):
        for rec in self:
            rec.thread_total_cones = rec.thread_bag_qty * rec.thread_cone_qty
