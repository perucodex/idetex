from odoo import _, api, fields, models
from odoo.exceptions import UserError


class ThreadBagConsumeWizard(models.TransientModel):
    _name = "thread.bag.consume.wizard"
    _description = "Selección de bolsas de hilo para el movimiento"

    move_id = fields.Many2one("stock.move", required=True, readonly=True)
    product_id = fields.Many2one(
        "product.product", related="move_id.product_id", readonly=True,
    )
    demand = fields.Float(
        string="Demanda (kg)", related="move_id.product_uom_qty", readonly=True,
        digits=(16, 3),
    )
    allowed_bag_ids = fields.Many2many(
        "thread.bag", "thread_bag_wizard_allowed_rel", "wizard_id", "bag_id",
        compute="_compute_allowed_bag_ids",
    )
    bag_ids = fields.Many2many(
        "thread.bag", "thread_bag_wizard_sel_rel", "wizard_id", "bag_id",
        string="Bolsas a usar",
        domain="[('id', 'in', allowed_bag_ids)]",
    )
    selected_net = fields.Float(
        string="Kg Seleccionados", compute="_compute_selected", digits=(16, 3),
    )
    selected_count = fields.Integer(string="Bolsas", compute="_compute_selected")
    diff_net = fields.Float(
        string="Diferencia vs Demanda (kg)", compute="_compute_selected", digits=(16, 3),
    )
    scan_input = fields.Char(
        string="Escanear correlativo",
        help="Escanea (o escribe) el código de la bolsa; se agrega automáticamente.",
    )

    @api.onchange("scan_input")
    def _onchange_scan_input(self):
        # El Code 39 viene como *CODIGO*; el escáner suele quitar los asteriscos,
        # pero por si acaso los limpiamos también aquí.
        code = (self.scan_input or "").strip().strip("*").strip()
        self.scan_input = False
        if not code:
            return
        Bag = self.env["thread.bag"]
        product = self.move_id.product_id
        bag = Bag.search([("name", "=", code), ("product_id", "=", product.id)], limit=1)
        if not bag:
            bag = Bag.search([("name", "=ilike", code), ("product_id", "=", product.id)], limit=1)
        if not bag:
            other = Bag.search([("name", "=ilike", code)], limit=1)
            if other:
                msg = _("La bolsa %(c)s es del producto %(p)s, no de %(m)s.",
                        c=code, p=other.product_id.display_name, m=product.display_name)
            else:
                msg = _("No existe una bolsa con correlativo %s.") % code
            return {"warning": {"title": _("Bolsa no válida"), "message": msg}}
        if bag in self.bag_ids:
            return {"warning": {"title": _("Repetida"),
                                "message": _("La bolsa %s ya está en la lista.") % bag.name}}
        if bag.state != "available" and bag not in self.move_id.thread_bag_ids:
            return {"warning": {"title": _("No disponible"),
                                "message": _("La bolsa %(c)s está %(s)s.",
                                             c=bag.name, s=bag.state)}}
        src = self.move_id.location_id
        if (src and bag not in self.move_id.thread_bag_ids
                and not bag.filtered_domain([("location_id", "child_of", src.id)])):
            return {"warning": {"title": _("Ubicación distinta"),
                                "message": _("La bolsa %(c)s está en %(loc)s, no en la ubicación de origen %(src)s.",
                                             c=bag.name, loc=bag.location_id.display_name, src=src.display_name)}}
        self.bag_ids = [(4, bag.id)]

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        move = self.env["stock.move"].browse(res.get("move_id"))
        if move and move.thread_bag_ids:
            res["bag_ids"] = [(6, 0, move.thread_bag_ids.ids)]
        return res

    @api.depends("move_id", "bag_ids")
    def _compute_allowed_bag_ids(self):
        Bag = self.env["thread.bag"]
        for wiz in self:
            product = wiz.move_id.product_id
            domain = [("product_id", "=", product.id), ("state", "=", "available")]
            # Solo bolsas en la ubicación de origen del movimiento (en la OF es la
            # "Ubicación de los componentes"); en una transferencia, su origen.
            src = wiz.move_id.location_id
            if src:
                domain.append(("location_id", "child_of", src.id))
            available = Bag.search(domain)
            wiz.allowed_bag_ids = available | wiz.move_id.thread_bag_ids

    @api.depends("bag_ids", "bag_ids.net_weight", "demand")
    def _compute_selected(self):
        for wiz in self:
            wiz.selected_net = sum(wiz.bag_ids.mapped("net_weight"))
            wiz.selected_count = len(wiz.bag_ids)
            wiz.diff_net = wiz.selected_net - (wiz.demand or 0.0)

    def action_confirm(self):
        self.ensure_one()
        # Se permite confirmar con 0 bolsas: limpia el detalle (deja el movimiento
        # sin líneas) y libera las bolsas previamente seleccionadas.
        self.move_id._thread_apply_bag_selection(self.bag_ids)
        return {"type": "ir.actions.act_window_close"}
