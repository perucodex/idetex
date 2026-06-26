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
        return {
            "type": "ir.actions.act_window",
            "name": _("Elegir bolsas de hilo"),
            "res_model": "thread.bag.consume.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_move_id": self.id},
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

    # ------------------------------------------------------------------
    # Validación: consumir / reubicar bolsas
    # ------------------------------------------------------------------
    def _action_done(self, cancel_backorder=False):
        done_moves = super()._action_done(cancel_backorder=cancel_backorder)
        for move in done_moves:
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
                bags.action_mark_consumed(picking=move.picking_id, location=dest)
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
