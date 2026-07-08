import base64
import io

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class ThreadBagConsumeWizardLine(models.TransientModel):
    """Línea de packing importada (una por bolsa) — PREVIA a la recepción.

    En recepción no se crean bolsas ni lotes al importar: solo se llenan estas
    líneas transitorias con lo leído del Excel. Al confirmar, el detalle del
    movimiento se arma con el lote como TEXTO (`lot_name`) y estos datos se
    guardan en el movimiento; recién al VALIDAR la recepción se crean los lotes
    (Odoo) y las bolsas (`thread.bag`).
    """

    _name = "thread.bag.consume.wizard.line"
    _description = "Línea de packing de hilo importada (previa a recepción)"

    wizard_id = fields.Many2one(
        "thread.bag.consume.wizard", required=True, ondelete="cascade", index=True,
    )
    name = fields.Char(string="Correlativo", required=True)
    lot_name = fields.Char(string="Lote", required=True)
    cone_qty = fields.Integer(string="Conos", default=1)
    net_weight = fields.Float(string="Peso Neto (kg)", digits=(16, 3))
    gross_weight = fields.Float(string="Peso Bruto (kg)", digits=(16, 3))
    tare = fields.Float(string="Tara (kg)", digits=(16, 3))
    cone_color = fields.Char(string="Color de Cono")
    packaging_type = fields.Char(string="Empaque")
    yarn_color = fields.Char(string="Color de Hilo")


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
    # Recepción: líneas del packing (transitorias, sin crear bolsas/lotes aún).
    line_ids = fields.One2many(
        "thread.bag.consume.wizard.line", "wizard_id", string="Bolsas del packing",
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
    is_reception = fields.Boolean(compute="_compute_is_reception")
    import_file = fields.Binary(string="Packing de Hilo (Excel)")
    import_filename = fields.Char(string="Nombre de archivo")

    @staticmethod
    def _move_is_reception(move):
        """La selección es una RECEPCIÓN (las bolsas aún no existen en esta compañía).

        Incluye la triangulación (dropship) y los tramos cuyo origen es TRÁNSITO
        inter-compañía (p.ej. Full Pima recibiendo desde el tránsito lo que Idetex
        compró con dropship): en ambos se importa el packing del proveedor.
        """
        if not move:
            return False
        return (
            move.location_id.usage in ("supplier", "transit")
            or move.picking_id.picking_type_id.code in ("incoming", "dropship")
        )

    @api.depends("move_id")
    def _compute_is_reception(self):
        for wiz in self:
            wiz.is_reception = self._move_is_reception(wiz.move_id)

    @api.onchange("scan_input")
    def _onchange_scan_input(self):
        # En recepción no se escanea (las líneas vienen del Excel importado).
        if self.is_reception:
            self.scan_input = False
            return
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
        # Consumo/transferencia: precargar las bolsas ya elegidas del movimiento.
        # (Recepción: las líneas del packing se cargan con el botón "Importar".)
        if move and not self._move_is_reception(move) and move.thread_bag_ids:
            res["bag_ids"] = [(6, 0, move.thread_bag_ids.ids)]
        return res

    @api.model
    def _create_for_move(self, move):
        """Crea el wizard para el movimiento REHIDRATANDO su estado persistido.

        El wizard es transitorio: cada apertura sería un registro vacío. Para que
        el packing no "se pierda" al reabrir, en recepción se recargan las líneas
        desde `move.thread_pending_bag_data` (lo guardado al Confirmar) como
        registros reales del wizard; en consumo se precargan las bolsas elegidas.
        """
        wiz = self.create({"move_id": move.id})
        if self._move_is_reception(move):
            data = move.thread_pending_bag_data or []
            if data:
                self.env["thread.bag.consume.wizard.line"].create([{
                    "wizard_id": wiz.id,
                    "name": r.get("name"),
                    "lot_name": r.get("lot_name"),
                    "cone_qty": r.get("cone_qty") or 1,
                    "net_weight": r.get("net_weight") or 0.0,
                    "gross_weight": r.get("gross_weight") or 0.0,
                    "tare": r.get("tare") or 0.0,
                    "cone_color": r.get("cone_color") or False,
                    "packaging_type": r.get("packaging_type") or False,
                    "yarn_color": r.get("yarn_color") or False,
                } for r in data])
        elif move.thread_bag_ids:
            wiz.bag_ids = [(6, 0, move.thread_bag_ids.ids)]
        return wiz

    @api.depends("move_id", "bag_ids")
    def _compute_allowed_bag_ids(self):
        Bag = self.env["thread.bag"]
        for wiz in self:
            move = wiz.move_id
            product = move.product_id
            if self._move_is_reception(move):
                # En recepción no se usan bolsas existentes (se crean al validar).
                wiz.allowed_bag_ids = wiz.bag_ids
                continue
            domain = [("product_id", "=", product.id), ("state", "=", "available")]
            # Solo bolsas en la ubicación de origen del movimiento (en la OF es la
            # "Ubicación de los componentes"); en una transferencia, su origen.
            src = move.location_id
            if src:
                domain.append(("location_id", "child_of", src.id))
            wiz.allowed_bag_ids = Bag.search(domain) | move.thread_bag_ids

    @api.depends("bag_ids", "bag_ids.net_weight", "line_ids", "line_ids.net_weight",
                 "demand", "is_reception")
    def _compute_selected(self):
        for wiz in self:
            if wiz.is_reception:
                wiz.selected_net = sum(wiz.line_ids.mapped("net_weight"))
                wiz.selected_count = len(wiz.line_ids)
            else:
                wiz.selected_net = sum(wiz.bag_ids.mapped("net_weight"))
                wiz.selected_count = len(wiz.bag_ids)
            wiz.diff_net = wiz.selected_net - (wiz.demand or 0.0)

    def _reload_action(self):
        """Reabre el mismo wizard (para reflejar las líneas persistidas)."""
        return {
            "type": "ir.actions.act_window",
            "res_model": "thread.bag.consume.wizard",
            "res_id": self.id,
            # `views` explícito: el cliente hace .map sobre esta lista; si falta,
            # rompe con "Cannot read properties of undefined (reading 'map')".
            "views": [[False, "form"]],
            "view_mode": "form",
            "target": "new",
            "context": dict(self.env.context),
        }

    def action_import_packing(self):
        """RECEPCIÓN: lee el Excel y GUARDA las líneas del packing como registros
        reales (`thread.bag.consume.wizard.line`) ligados al wizard.

        Al persistirlas en la BD, la lista se pagina normal y el Confirmar las lee
        TODAS (sin depender del límite del widget), soportando cualquier cantidad
        de bolsas. NO crea lotes ni `thread.bag`: eso ocurre solo al VALIDAR el
        picking. Solo carga las filas del producto de esta línea (avisa de otros).
        """
        self.ensure_one()
        if not self.import_file:
            raise UserError(_("Suba el archivo Excel del packing."))
        product = self.move_id.product_id
        company = self.move_id.company_id
        try:
            import openpyxl  # noqa: F401
        except ImportError:
            raise UserError(_("Se requiere la librería openpyxl."))
        raw = base64.b64decode(self.import_file)
        try:
            wb = openpyxl.load_workbook(io.BytesIO(raw), data_only=True)
        except Exception as exc:  # noqa: BLE001
            raise UserError(_("No se pudo leer el Excel: %s") % exc)

        parser = self.env["thread.bag.import"].new({"company_id": company.id})
        ws = header_row = cols = None
        for sheet in wb.worksheets:
            hr, cm = parser._find_header(sheet)
            if hr:
                ws, header_row, cols = sheet, hr, cm
                break
        if not ws:
            raise UserError(_(
                "No se encontró una hoja con columnas Correl, Articulo, Lote y Kilos."))

        # create_lots=False: sin crear lotes (se crean al validar).
        # check_existing=False: NO omitir correlativos ya existentes — aquí solo se
        # arma el detalle; la deduplicación real (por compañía) ocurre al crear las
        # bolsas en la validación. Antes esto dejaba el import en 0 líneas cuando
        # los correlativos ya existían en OTRA operación/compañía.
        rows, missing_codes, skipped_dup, skipped_invalid = parser._parse_rows(
            ws, header_row, cols, create_lots=False, check_existing=False)
        prod_rows = [r for r in rows if r["product"] == product]

        # Persistir las líneas (reemplazando las anteriores de este wizard).
        Line = self.env["thread.bag.consume.wizard.line"]
        Line.search([("wizard_id", "=", self.id)]).unlink()
        Line.create([{
            "wizard_id": self.id,
            "name": r["correl"],
            "lot_name": r["lot_name"],
            "cone_qty": r["cones"] or 1,
            "net_weight": r["net"],
            "gross_weight": r["gross"],
            "tare": r["tare"],
            "cone_color": r["cone_color"],
            "packaging_type": r["packaging"],
            "yarn_color": r["yarn_color"],
        } for r in prod_rows])
        self.import_file = False
        self.import_filename = False

        # Notificación (NO sticky) + recarga del wizard. El `next` funciona porque
        # _reload_action incluye `views` explícito (el cliente hace .map sobre esa
        # lista y no la deriva de view_mode en esta ruta).
        msg = [_("Bolsas cargadas para %s: %s") % (
            product.default_code or product.display_name, len(prod_rows))]
        other = sorted({(r["product"].default_code or r["product"].display_name)
                        for r in rows if r["product"] != product})
        if other:
            msg.append(_("El Excel trae otros productos; impórtalos desde la línea "
                         "de cada uno: %s") % ", ".join(other))
        if missing_codes:
            msg.append(_("Artículos del Excel no existentes en Odoo: %s")
                       % ", ".join(sorted(missing_codes)))
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Packing importado"),
                "message": "\n".join(msg),
                "type": "warning" if (other or missing_codes) else "success",
                "sticky": False,
                "next": self._reload_action(),
            },
        }

    def action_clear_lines(self):
        """Elimina todas las líneas del packing (y el archivo subido)."""
        self.ensure_one()
        self.line_ids.unlink()
        self.import_file = False
        self.import_filename = False
        return self._reload_action()

    def action_confirm(self):
        self.ensure_one()
        if self.is_reception:
            # Recepción: arma el detalle con el lote como TEXTO y guarda los datos
            # por bolsa en el movimiento. Lotes y bolsas se crean al VALIDAR.
            self.move_id._thread_apply_reception_lines(self.line_ids)
        else:
            # Se permite confirmar con 0 bolsas: limpia el detalle (deja el movimiento
            # sin líneas) y libera las bolsas previamente seleccionadas.
            self.move_id._thread_apply_bag_selection(self.bag_ids)
        return {"type": "ir.actions.act_window_close"}
