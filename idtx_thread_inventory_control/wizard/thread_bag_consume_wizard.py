import base64
import io
import math

from odoo import _, api, fields, models
from odoo.exceptions import UserError


def _pick_indices_for_target(weights, target):
    """Elige el subconjunto de `weights` cuya suma sea >= `target` con el MENOR
    exceso posible (la combinación ÓPTIMA que más se acerca a la demanda, nunca
    por debajo si el total alcanza).

    Exacto vía subset-sum con bitsets (granularidad 0.01 kg, pesos truncados
    hacia abajo para garantizar suma real >= target). Si el problema es muy
    grande (n * rango de sumas), cae a un greedy descendente + mejor ajuste
    (agregar la bolsa mínima que cubra el hueco o el mejor intercambio 1x1),
    que deja excesos de fracciones de kg.

    Devuelve la lista de índices elegidos. Si la suma total no alcanza el
    target, devuelve TODOS los índices (mejor esfuerzo, queda por debajo).
    """
    n = len(weights)
    if not n or target <= 0:
        return []
    if sum(weights) < target:
        return list(range(n))

    scale = 100  # centésimas de kg (10 g)
    w_int = [int(w * scale + 1e-9) for w in weights]  # truncar hacia abajo
    T = int(math.ceil(target * scale - 1e-9))
    B = T + max(w_int)  # el óptimo está en [T, T + w_max]

    # DP exacto solo si el trabajo es razonable. n*B = bits procesados; los
    # enteros de Python operan 64 bits/palabra, así que 2e10 ≈ pocos segundos
    # (cubre p.ej. 2,500 bolsas contra 60,000 kg de demanda).
    if n * B <= 20_000_000_000:
        CHUNK = 64
        full = (1 << (B + 1)) - 1
        checkpoints = []  # máscara ANTES de cada bloque
        mask = 1
        for start in range(0, n, CHUNK):
            checkpoints.append(mask)
            for i in range(start, min(start + CHUNK, n)):
                if w_int[i]:
                    mask = (mask | (mask << w_int[i])) & full
        # menor suma alcanzable en [T, B]
        window = mask >> T
        if not window:
            return list(range(n))  # no debería pasar (total >= target)
        best = ((window & -window).bit_length() - 1) + T
        # reconstrucción por bloques (recalcula máscaras dentro del bloque)
        chosen = []
        remaining = best
        for b in range(len(checkpoints) - 1, -1, -1):
            start = b * CHUNK
            end = min(start + CHUNK, n)
            masks = [checkpoints[b]]
            for i in range(start, end):
                m = masks[-1]
                if w_int[i]:
                    m = (m | (m << w_int[i])) & full
                masks.append(m)
            for i in range(end - 1, start - 1, -1):
                before = masks[i - start]
                if w_int[i] and remaining >= w_int[i] and not ((before >> remaining) & 1):
                    chosen.append(i)
                    remaining -= w_int[i]
            # si remaining ya es alcanzable al inicio del bloque, seguir subiendo
        return sorted(chosen)

    # ---- Fallback casi-óptimo: greedy descendente + mejor ajuste ----
    order = sorted(range(n), key=lambda i: -weights[i])
    sel, total = [], 0.0
    for i in order:
        if total + weights[i] <= target:
            sel.append(i)
            total += weights[i]
    gap = target - total
    if gap <= 1e-9:
        return sorted(sel)
    sel_set = set(sel)
    unsel = sorted((i for i in range(n) if i not in sel_set), key=lambda i: weights[i])
    # Opción A: agregar la bolsa más chica (todas las no elegidas son > gap).
    best_excess = weights[unsel[0]] - gap
    best_plan = ("add", unsel[0])
    # Opción B: mejor intercambio 1x1 (sale s, entra u; u - s >= gap mínimo).
    sel_asc = sorted(sel, key=lambda i: weights[i])
    j = 0
    for u in unsel:
        wu = weights[u]
        # el s más grande con wu - ws >= gap
        cand = None
        for s in sel_asc:
            if wu - weights[s] >= gap - 1e-9:
                cand = s
            else:
                break
        if cand is not None:
            exc = (wu - weights[cand]) - gap
            if exc < best_excess - 1e-9:
                best_excess = exc
                best_plan = ("swap", cand, u)
    if best_plan[0] == "add":
        sel.append(best_plan[1])
    else:
        sel.remove(best_plan[1])
        sel.append(best_plan[2])
    return sorted(sel)


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
        """Importar TODO el packing (todas las filas del producto)."""
        return self._import_packing(limit_to_demand=False)

    def action_import_packing_demand(self):
        """Importar SOLO hasta cubrir la demanda: acumula bolsas en el orden del
        Excel y se detiene apenas el total alcanza/supera la demanda (incluye la
        bolsa que cruza el umbral: demanda 1000 y 40 bolsas = 998.7 → entra la
        41 y el total queda en ~1023, nunca por debajo de la demanda si alcanza).
        """
        return self._import_packing(limit_to_demand=True)

    def _import_packing(self, limit_to_demand=False):
        """Lee el Excel del packing y actúa según el modo del wizard.

        RECEPCIÓN: guarda las filas como líneas reales del wizard
        (`thread.bag.consume.wizard.line`) — al persistirlas la lista se pagina
        normal y el Confirmar las lee TODAS de la BD, sin límite. NO crea lotes
        ni `thread.bag` (eso ocurre al VALIDAR el picking).

        CONSUMO / ENTREGA: SELECCIONA las bolsas EXISTENTES por correlativo (en
        vez de escanearlas una por una) y las agrega a la selección; reporta las
        no encontradas / no disponibles / en otra ubicación. No crea nada.

        Con `limit_to_demand=True` solo se toma lo necesario para cubrir la
        demanda del movimiento (en el orden del Excel).
        """
        self.ensure_one()
        if not self.import_file:
            raise UserError(_("Suba el archivo Excel del packing."))
        if limit_to_demand and self.demand <= 0:
            raise UserError(_(
                "La demanda del movimiento es 0: usa 'Importar todo'."))
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
        other = sorted({(r["product"].default_code or r["product"].display_name)
                        for r in rows if r["product"] != product})
        self.import_file = False
        self.import_filename = False

        if self.is_reception:
            if limit_to_demand:
                # Combinación ÓPTIMA: subconjunto con suma >= demanda y exceso
                # mínimo, calculado ANTES de crear las líneas.
                idx = _pick_indices_for_target(
                    [r["net"] for r in prod_rows], self.demand)
                prod_rows = [prod_rows[i] for i in idx]
                total = sum(r["net"] for r in prod_rows)
                msg_extra = _("(óptimo para demanda %.2f kg: %.2f kg, diferencia %+.2f)") % (
                    self.demand, total, total - self.demand)
            else:
                msg_extra = ""
            self._load_packing_lines(prod_rows)
            msg = [(_("Bolsas cargadas para %s: %s %s") % (
                product.default_code or product.display_name,
                len(prod_rows), msg_extra)).strip()]
        else:
            msg, _found = self._select_existing_bags(
                [r["correl"] for r in prod_rows],
                max_net=self.demand if limit_to_demand else None)

        if other:
            msg.append(_("El Excel trae otros productos; impórtalos desde la línea "
                         "de cada uno: %s") % ", ".join(other))
        if missing_codes:
            msg.append(_("Artículos del Excel no existentes en Odoo: %s")
                       % ", ".join(sorted(missing_codes)))
        # Notificación (NO sticky) + recarga del wizard. El `next` funciona porque
        # _reload_action incluye `views` explícito (el cliente hace .map sobre esa
        # lista y no la deriva de view_mode en esta ruta).
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

    def _load_packing_lines(self, prod_rows):
        """Persiste las filas del Excel como líneas del wizard (reemplaza las
        anteriores). Usado por la recepción y por la declaración de packing."""
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

    def _select_existing_bags(self, correls, max_net=None):
        """CONSUMO/ENTREGA: agrega a la selección las bolsas EXISTENTES cuyos
        correlativos vienen en el packing. Mismas validaciones que el escaneo
        (disponible + en la ubicación de origen). Devuelve (resumen, n_halladas).

        Con `max_net` se eligen, ENTRE TODAS las bolsas válidas del Excel, las
        que dan la suma >= al neto faltante con exceso MÍNIMO (óptimo, no en el
        orden del archivo), partiendo de lo YA seleccionado.
        """
        move = self.move_id
        Bag = self.env["thread.bag"]
        found = {b.name: b for b in Bag.search([
            ("name", "in", correls),
            ("product_id", "=", move.product_id.id),
            ("company_id", "=", move.company_id.id),
        ])}
        src = move.location_id
        current = move.thread_bag_ids
        missing, unavailable, wrong_loc = [], [], []
        already = Bag      # ya elegidas que reaparecen (se re-aceptan, no suman)
        candidates = []    # bolsas nuevas VÁLIDAS (candidatas a entrar)
        for correl in correls:
            bag = found.get(correl)
            if not bag:
                missing.append(correl)
            elif bag in current or bag in self.bag_ids:
                already |= bag
            elif bag.state != "available":
                unavailable.append(correl)
            elif src and not bag.filtered_domain([("location_id", "child_of", src.id)]):
                wrong_loc.append(correl)
            else:
                candidates.append(bag)
        if max_net is not None:
            # Falta por cubrir = demanda objetivo - lo ya seleccionado.
            residual = max_net - sum(self.bag_ids.mapped("net_weight"))
            if residual > 1e-9 and candidates:
                idx = _pick_indices_for_target(
                    [b.net_weight for b in candidates], residual)
                candidates = [candidates[i] for i in idx]
            else:
                candidates = []
        to_add = already
        for b in candidates:
            to_add |= b
        total = sum(self.bag_ids.mapped("net_weight")) + sum(
            b.net_weight for b in candidates)
        if to_add:
            self.bag_ids = [(4, b.id) for b in to_add]

        def _sample(items):
            s = ", ".join(items[:10])
            return s + ("…" if len(items) > 10 else "")

        msg = [_("Bolsas seleccionadas del Excel: %s de %s")
               % (len(to_add), len(correls))]
        if max_net is not None:
            msg.append(_("Cobertura de la demanda (%.2f kg): %.2f kg (diferencia %+.2f)")
                       % (max_net, total, total - max_net))
        if missing:
            msg.append(_("No existen en esta compañía (%s): %s")
                       % (len(missing), _sample(missing)))
        if unavailable:
            msg.append(_("No disponibles —reservadas/consumidas— (%s): %s")
                       % (len(unavailable), _sample(unavailable)))
        if wrong_loc:
            msg.append(_("En otra ubicación distinta al origen (%s): %s")
                       % (len(wrong_loc), _sample(wrong_loc)))
        return msg, len(found)

    def action_clear_lines(self):
        """Vacía la lista (líneas del packing o selección de bolsas) y el archivo."""
        self.ensure_one()
        self.line_ids.unlink()
        self.bag_ids = [(5, 0, 0)]
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
