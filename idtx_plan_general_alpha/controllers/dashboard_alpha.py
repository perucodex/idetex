import datetime
import logging
import re
import pytz
from collections import defaultdict
from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


def _covered_cells(anchor, span_cols, span_rows, cols):
    w = max(1, span_cols or 1)
    h = max(1, span_rows or 1)
    return {anchor + r * cols + c for r in range(h) for c in range(w)}


def _machine_num(name):
    """Extrae el número de máquina (ej. 'JERSERA MAQ 12' -> 12); None si el
    nombre no tiene número. Mismo criterio que machineNum() en machine_floor.js."""
    n = (name or "").upper()
    m = re.search(r"MAQ\s+(\d+)", n)
    if m:
        return int(m.group(1))
    nums = re.findall(r"\d+", n)
    return int(nums[-1]) if nums else None


def _factory_sort_key(name):
    """Orden real de fábrica: por número de máquina. Dentro de un mismo
    centro de trabajo el número NO se repite entre tipos (es una secuencia
    única de instalación 1..N que mezcla LISTADORA/JERSERA/RIPERA/etc, no
    algo agrupado por tipo) — por eso se ordena solo por número, sin agrupar.
    Las máquinas sin número (p.ej. 'BIANCALANI') van al final, por nombre."""
    num = _machine_num(name)
    if num is not None:
        return (0, num, "")
    return (1, 0, (name or "").upper())


class PlanAlphaDashboard(http.Controller):

    # Nombre de área (TEJEDURIA/TINTORERIA) -> palabras clave del departamento
    # HR donde viven las máquinas. Se usa departamento (no mrp.workcenter)
    # porque un equipo de IDETEX no puede apuntar al centro de trabajo real
    # de otra compañía sin romper check_company — ver
    # [[project_workcenter_check_company]]. El departamento es único (sin
    # copias homónimas por compañía), así que no hace falta crear ni tocar
    # ningún mrp.workcenter para este emparejamiento.
    _WORKCENTER_DEPT_KEYWORDS = {
        "TEJEDURIA":  ["TEJED", "TEJID"],
        "TINTORERIA": ["TINTOR", "TINTE"],
    }

    def _equipment_domain_for_workcenter(self, env, workcenter):
        """Dominio de búsqueda de maintenance.equipment para un área dada,
        o None si el área no existe / no aplica. Compartido por floor_data
        y reset_factory_order."""
        kws = self._WORKCENTER_DEPT_KEYWORDS.get((workcenter or "").upper(), [])
        if not kws:
            return None
        Dept = env["hr.department"].sudo()
        dept_ids = []
        for kw in kws:
            dept_ids += Dept.search([("name", "ilike", kw)]).ids
        if not dept_ids:
            return None
        return [("active", "=", True), ("department_id", "in", dept_ids)]

    @http.route(
        "/idtx_plan_alpha/workcenters",
        type="jsonrpc",
        auth="user",
        methods=["POST"],
    )
    def alpha_workcenters(self):
        """Return the fixed list of áreas (TEJEDURIA/TINTORERIA) with their
        active machine count, por departamento — ver _equipment_domain_for_workcenter."""
        env = request.env
        Equipment = env["maintenance.equipment"].sudo()
        workcenters = []
        for name in ("TEJEDURIA", "TINTORERIA"):
            domain = self._equipment_domain_for_workcenter(env, name)
            count = Equipment.search_count(domain) if domain else 0
            workcenters.append({"name": name, "count": count})
        return {"workcenters": workcenters}

    @http.route(
        "/idtx_plan_alpha/floor_data",
        type="jsonrpc",
        auth="user",
        methods=["POST"],
    )
    def floor_data(self, workcenter=None):
        env = request.env
        if not workcenter:
            return {"machines": [], "workcenter": workcenter}

        Equipment = env["maintenance.equipment"].sudo()
        domain = self._equipment_domain_for_workcenter(env, workcenter)
        if domain is None:
            return {"machines": [], "workcenter": workcenter}

        equipments = Equipment.search(domain, order="name asc")

        GRID_COLS_OLD = 20
        GRID_COLS_NEW = 24

        Layout = env["idtx.alpha.floor.layout"].sudo()
        existing = Layout.search([("workcenter", "=", workcenter)])
        layout_map = {l.equipment_id.id: l.slot_index for l in existing}
        span_map = {l.equipment_id.id: (l.span_cols, l.span_rows) for l in existing}
        occupied = set()
        for eq_id, anchor in layout_map.items():
            cols, rows = span_map.get(eq_id, (1, 1))
            occupied |= _covered_cells(anchor, cols, rows, GRID_COLS_NEW)

        if not layout_map and "idtx.machine.layout" in env.registry.models:
            OldLayout = env["idtx.machine.layout"].sudo()
            area_kw = workcenter.lower()
            old_records = OldLayout.search([("area", "ilike", area_kw)])
            if old_records:
                sorted_old = sorted(old_records, key=lambda r: r.slot_index or 0)
                seq_slot = 0
                to_create_from_old = []
                for rec in sorted_old:
                    eq_id = rec.equipment_id.id if rec.equipment_id else None
                    if not eq_id or eq_id in layout_map:
                        continue
                    while seq_slot in occupied:
                        seq_slot += 1
                    layout_map[eq_id] = seq_slot
                    occupied.add(seq_slot)
                    to_create_from_old.append({
                        "equipment_id": eq_id,
                        "workcenter": workcenter,
                        "slot_index": seq_slot,
                    })
                    seq_slot += 1
                if to_create_from_old:
                    Layout.create(to_create_from_old)

        # Auto-assign sequential slots for machines that have no position yet
        next_slot = 0
        to_create = []
        for eq in equipments:
            if eq.id not in layout_map:
                while next_slot in occupied:
                    next_slot += 1
                layout_map[eq.id] = next_slot
                occupied.add(next_slot)
                to_create.append({
                    "equipment_id": eq.id,
                    "workcenter": workcenter,
                    "slot_index": next_slot,
                })
                next_slot += 1
        if to_create:
            Layout.create(to_create)

        has_state = "machine_state" in Equipment._fields

        # Trabajo actual — solo para las máquinas agrandadas (span > 1), para no
        # pagar el costo de esta búsqueda en las decenas/cientos de máquinas normales.
        current_job = {}
        big_ids = [eq.id for eq in equipments if span_map.get(eq.id, (1, 1)) != (1, 1)]
        if big_ids and "mrp.workorder" in env.registry.models:
            Workorder = env["mrp.workorder"].sudo()
            for eq_id in big_ids:
                wo = Workorder.search([
                    ("option_ids.equipment_ids", "in", eq_id),
                    ("state", "=", "progress"),
                ], order="date_start desc", limit=1)
                if wo:
                    current_job[eq_id] = {
                        "production": wo.production_id.name or "",
                        "product":    wo.product_id.display_name or "",
                        "progress":   round(wo.qty_produced or 0, 1) / (wo.qty_production or 1) * 100
                                      if wo.qty_production else 0,
                    }

        machines = []
        for eq in equipments:
            machines.append({
                "id":            eq.id,
                "name":          eq.name or "",
                "model":         eq.model or "",
                "serial":        eq.serial_no or "",
                "enabled":       bool(eq.enabled) if hasattr(eq, "enabled") else True,
                "oos":           bool(eq.oos) if hasattr(eq, "oos") else False,
                "machine_state": eq.machine_state if has_state else None,
                "slot_index":    layout_map.get(eq.id, 0),
                "span_cols":     span_map.get(eq.id, (1, 1))[0],
                "span_rows":     span_map.get(eq.id, (1, 1))[1],
                "current_job":   current_job.get(eq.id),
            })
        return {"machines": machines, "workcenter": workcenter}

    @http.route(
        "/idtx_plan_alpha/machine_detail",
        type="jsonrpc",
        auth="user",
        methods=["POST"],
    )
    def machine_detail(self, equipment_id=None):
        """Devuelve la ficha técnica completa de una máquina."""
        if not equipment_id:
            return {"machine": None}
        env = request.env
        eq = env["maintenance.equipment"].sudo().browse(int(equipment_id))
        if not eq.exists():
            return {"machine": None}

        fields_eq = eq._fields
        machine = {
            "id":          eq.id,
            "name":        eq.name or "",
            "model":       eq.model or "",
            "serial":      eq.serial_no or "",
            "machine_state": eq.machine_state if "machine_state" in fields_eq else None,
            "enabled":     bool(eq.enabled) if "enabled" in fields_eq else True,
            "workcenter":  eq.workcenter_id.name if "workcenter_id" in fields_eq and eq.workcenter_id else "",
            "department":  eq.department_id.name if eq.department_id else "",
            "technician":  eq.technician_user_id.name if eq.technician_user_id else "",
            "category":    eq.category_id.name if eq.category_id else "",
            "note":        (eq.note or "")[:300],
            "purchase_date": str(eq.effective_date) if eq.effective_date else "",
            "warranty_date": str(eq.warranty_date) if eq.warranty_date else "",
            "capacity":    eq.capacity_power if "capacity_power" in fields_eq else "",
            "year":        eq.manufacture_year if "manufacture_year" in fields_eq else "",
        }

        # Los datetime del ORM son naive en UTC; para mostrarlos hay que
        # convertirlos a la zona horaria del USUARIO logueado (no del sudo).
        _tz = pytz.timezone(request.env.user.tz or "UTC")

        def _fmt_local(dt):
            if not dt:
                return ""
            return pytz.utc.localize(dt).astimezone(_tz).strftime("%Y-%m-%d %H:%M")

        # Lo que se está TEJIENDO ahora en esta máquina: órdenes de trabajo en
        # progreso cuya opción usa este equipo. Se usa sudo porque las OT pueden
        # ser de otra compañía (FULL PIMA) mientras la máquina es de IDETEX.
        tejiendo = []
        # Historial de lo ya tejido en esta máquina: OT terminadas, con sus
        # fechas de inicio/fin y duración real.
        historial = []
        if "mrp.workorder" in env.registry.models:
            try:
                Workorder = env["mrp.workorder"].sudo()
                wos = Workorder.search([
                    ("option_ids.equipment_ids", "in", eq.id),
                    ("state", "=", "progress"),
                ], order="date_start desc", limit=20)
                for wo in wos:
                    tejiendo.append({
                        "id":         wo.id,
                        "workorder":  wo.display_name or wo.name or "",
                        "production": wo.production_id.name or "",
                        "product":    wo.product_id.display_name or "",
                        "qty":        round(wo.qty_production or 0, 2),
                        "produced":   round(wo.qty_produced or 0, 2),
                        "uom":        wo.production_id.product_uom_id.name if wo.production_id.product_uom_id else "",
                        "workcenter": wo.workcenter_id.name or "",
                        "rate":       round(wo.estimated_rate_kg_h or 0, 1) if "estimated_rate_kg_h" in wo._fields else 0,
                        "date_start": _fmt_local(wo.date_start),
                    })

                done_wos = Workorder.search([
                    ("option_ids.equipment_ids", "in", eq.id),
                    ("state", "=", "done"),
                ], order="date_finished desc, date_start desc", limit=30)
                for wo in done_wos:
                    historial.append({
                        "id":            wo.id,
                        "workorder":     wo.display_name or wo.name or "",
                        "production":    wo.production_id.name or "",
                        "product":       wo.product_id.display_name or "",
                        "qty":           round(wo.qty_production or 0, 2),
                        "produced":      round(wo.qty_produced or 0, 2),
                        "uom":           wo.production_id.product_uom_id.name if wo.production_id.product_uom_id else "",
                        "date_start":    _fmt_local(wo.date_start),
                        "date_finished": _fmt_local(wo.date_finished),
                        "duration":      round(wo.duration or 0, 1),
                    })
            except Exception:
                _logger.warning("machine_detail: error cargando tejido/historial", exc_info=True)

        return {"machine": machine, "tejiendo": tejiendo, "historial": historial}

    @http.route(
        "/idtx_plan_alpha/save_floor_position",
        type="jsonrpc",
        auth="user",
        methods=["POST"],
    )
    def save_floor_position(self, equipment_id=None, workcenter=None, slot_index=None,
                             span_cols=1, span_rows=1):
        """Persist a machine's grid slot position and combined size (up to 4x4 cells)."""
        if not equipment_id or not workcenter or slot_index is None:
            return {"ok": False}
        if span_cols not in (1, 2, 3, 4):
            span_cols = 1
        if span_rows not in (1, 2, 3, 4):
            span_rows = 1
        env = request.env
        Layout = env["idtx.alpha.floor.layout"].sudo()
        existing = Layout.search(
            [("equipment_id", "=", equipment_id), ("workcenter", "=", workcenter)], limit=1
        )
        vals = {"slot_index": slot_index, "span_cols": span_cols, "span_rows": span_rows}
        if existing:
            existing.write(vals)
        else:
            Layout.create({"equipment_id": equipment_id, "workcenter": workcenter, **vals})
        return {"ok": True}

    @http.route(
        "/idtx_plan_alpha/reset_factory_order",
        type="jsonrpc",
        auth="user",
        methods=["POST"],
    )
    def reset_factory_order(self):
        """Reordena TODAS las máquinas de TODOS los centros de trabajo según
        su numeración de fábrica (orden real de instalación, ver _factory_sort_key)
        y deshace cualquier combinación de cuadros (vuelve a 1x1)."""
        env = request.env
        Equipment = env["maintenance.equipment"].sudo()
        Layout = env["idtx.alpha.floor.layout"].sudo()

        workcenters = self.alpha_workcenters()["workcenters"]

        to_create = []
        for wc in workcenters:
            domain = self._equipment_domain_for_workcenter(env, wc["name"])
            if domain is None:
                continue
            equipments = Equipment.search(domain)
            ordered = equipments.sorted(key=lambda eq: _factory_sort_key(eq.name))
            for i, eq in enumerate(ordered):
                to_create.append({
                    "equipment_id": eq.id, "workcenter": wc["name"],
                    "slot_index": i, "span_cols": 1, "span_rows": 1,
                })

        Layout.search([]).unlink()
        if to_create:
            Layout.create(to_create)
        return {"ok": True}

    @http.route(
        "/idtx_plan_alpha/dashboard_data",
        type="jsonrpc",
        auth="user",
        methods=["POST"],
    )
    def dashboard_data(self):
        # ── Fuente: PEDIDOS DE VENTA (sale.order) ─────────────────────────────
        # Confirmados/Cotizaciones se clasifican por `is_quote` (NO por `state`):
        # es el mismo campo que usan los menús reales de Ventas de idtx_sale_order
        # ("Cotizaciones" = is_quote=True, "Pedidos de Venta" = is_quote=False —
        # ver sale_quotation_views.xml). `state` sigue determinando Cancelados y
        # el sub-desglose Borrador/Enviada dentro de las cotizaciones.
        # Kilos = suma de product_uom_qty (líneas en kg) · Monto = amount_total.
        env = request.env
        SO = env["sale.order"].sudo()
        ESTADO_LBL = {"draft": "Borrador", "sent": "Enviada",
                      "sale": "Confirmado", "cancel": "Cancelado"}

        def _kg(orders):
            return round(sum(l.product_uom_qty for o in orders for l in o.order_line
                             if not l.display_type), 1)

        def _kg_pend(orders):
            return round(sum((l.product_uom_qty - l.qty_delivered)
                             for o in orders for l in o.order_line
                             if not l.display_type), 1)

        confirmados  = SO.search([("is_quote", "=", False), ("state", "!=", "cancel")])
        cotizaciones = SO.search([("is_quote", "=", True), ("state", "!=", "cancel")])
        borrador     = cotizaciones.filtered(lambda o: o.state == "draft")
        enviadas     = cotizaciones.filtered(lambda o: o.state == "sent")
        cancelados   = SO.search([("state", "=", "cancel")])
        todos        = SO.search([])
        vigentes     = confirmados | cotizaciones          # todo menos cancelados

        kilos_produccion = _kg(confirmados)
        kilos_cotizado   = _kg(cotizaciones)
        kilos_entregado  = round(sum(l.qty_delivered for o in confirmados
                                     for l in o.order_line if not l.display_type), 1)
        kilos_pendientes = _kg_pend(confirmados)
        monto_produccion = round(sum(confirmados.mapped("amount_total")), 2)
        monto_cotizado   = round(sum(cotizaciones.mapped("amount_total")), 2)

        no_cancel = len(confirmados) + len(cotizaciones)
        pct_confirmados = round(len(confirmados) / no_cancel * 100, 1) if no_cancel else 0.0

        # ── Distribución por estado (donut) ───────────────────────────────────
        estado_dist = [
            {"estado": "Confirmados", "count": len(confirmados), "color": "#22c55e"},
            {"estado": "Borrador",    "count": len(borrador),    "color": "#f59e0b"},
            {"estado": "Enviadas",    "count": len(enviadas),    "color": "#3b82f6"},
            {"estado": "Cancelados",  "count": len(cancelados),  "color": "#94a3b8"},
        ]

        # ── Kg por estado (barras) ────────────────────────────────────────────
        estado_kg = [
            {"label": "Confirmado", "kg": kilos_produccion},
            {"label": "Cotizado",   "kg": kilos_cotizado},
            {"label": "Cancelado",  "kg": _kg(cancelados)},
        ]

        # ── Top clientes por kg (vigentes) ────────────────────────────────────
        cli = defaultdict(lambda: {"kilos": 0.0, "count": 0})
        for o in vigentes:
            k = (o.partner_id.name or "Sin Cliente").strip()
            cli[k]["kilos"] += _kg(o)
            cli[k]["count"] += 1
        top_clientes = sorted(
            [{"customer": k, "kilos": round(v["kilos"], 1), "count": v["count"]}
             for k, v in cli.items()],
            key=lambda x: x["kilos"], reverse=True)[:10]

        # ── Top pedidos por kg ────────────────────────────────────────────────
        top_pedidos = sorted(
            [{"num": o.name or "", "customer": (o.partner_id.name or "").strip()[:26],
              "kg": _kg(o), "state": o.state, "estado": ESTADO_LBL.get(o.state, o.state)}
             for o in vigentes],
            key=lambda x: x["kg"], reverse=True)[:8]

        # ── Tendencia mensual (últimos 6 meses) ───────────────────────────────
        today   = datetime.date.today()
        six_ago = today - datetime.timedelta(days=180)
        recientes = SO.search([("date_order", ">=", six_ago)])
        monthly = defaultdict(lambda: {"cotizaciones": 0, "confirmados": 0})
        for o in recientes:
            if not o.date_order or o.state == "cancel":
                continue
            key = o.date_order.strftime("%b %Y")
            if o.is_quote:
                monthly[key]["cotizaciones"] += 1
            else:
                monthly[key]["confirmados"] += 1
        months_order = []
        d = datetime.date(six_ago.year, six_ago.month, 1)
        while d <= today:
            months_order.append(d.strftime("%b %Y"))
            d = d.replace(year=d.year + 1, month=1) if d.month == 12 else d.replace(month=d.month + 1)
        tendencia = [
            {"mes": m, "cotizaciones": monthly[m]["cotizaciones"],
             "confirmados": monthly[m]["confirmados"],
             "total": monthly[m]["cotizaciones"] + monthly[m]["confirmados"]}
            for m in months_order
        ]

        # ── Kg por producto y por color (líneas) ──────────────────────────────
        prod_map  = defaultdict(float)
        color_map = defaultdict(lambda: {"kg": 0.0, "count": 0})
        for o in vigentes:
            for l in o.order_line:
                if l.display_type:
                    continue
                qty = l.product_uom_qty or 0.0
                pname = (l.product_id.display_name or "—").strip()
                prod_map[pname] += qty
                cname = (l.color_name or "Sin color").strip() or "Sin color"
                color_map[cname]["kg"] += qty
                color_map[cname]["count"] += 1
        por_producto = sorted(
            [{"producto": k[:28], "kg": round(v, 1)} for k, v in prod_map.items()],
            key=lambda x: x["kg"], reverse=True)[:10]
        por_color = sorted(
            [{"color": k[:24], "kg": round(v["kg"], 1), "count": v["count"]}
             for k, v in color_map.items()],
            key=lambda x: x["kg"], reverse=True)[:10]

        # ── Detalle de pedidos (tabla) ────────────────────────────────────────
        detalle = sorted(
            [{"num": o.name or "", "customer": (o.partner_id.name or "").strip()[:30],
              "kg": _kg(o), "monto": round(o.amount_total, 2), "state": o.state,
              "estado": ESTADO_LBL.get(o.state, o.state),
              "fecha": str(o.date_order)[:10] if o.date_order else ""}
             for o in vigentes],
            key=lambda x: x["kg"], reverse=True)[:15]

        # ── Desglose por vendedor ──────────────────────────────────────────────
        # Este dashboard agrega TODOS los vendedores; la vista "Cotizaciones" de
        # Ventas filtra por defecto a "Mis Cotizaciones" (user_id = uid). Esta
        # tabla permite reconciliar el total de arriba contra lo que cada
        # vendedor ve en su propia vista.
        vend = defaultdict(lambda: {"vendedor": "Sin vendedor", "cotizaciones": 0,
                                     "kg_cotizado": 0.0, "confirmados": 0, "kg_confirmado": 0.0})
        for o in cotizaciones:
            v = vend[o.user_id.id]
            v["vendedor"] = o.user_id.name or "Sin vendedor"
            v["cotizaciones"] += 1
            v["kg_cotizado"] += _kg(o)
        for o in confirmados:
            v = vend[o.user_id.id]
            v["vendedor"] = o.user_id.name or "Sin vendedor"
            v["confirmados"] += 1
            v["kg_confirmado"] += _kg(o)
        por_vendedor = sorted(
            [{"user_id": uid, "vendedor": v["vendedor"],
              "cotizaciones": v["cotizaciones"], "kg_cotizado": round(v["kg_cotizado"], 1),
              "confirmados": v["confirmados"], "kg_confirmado": round(v["kg_confirmado"], 1)}
             for uid, v in vend.items()],
            key=lambda x: x["kg_cotizado"] + x["kg_confirmado"], reverse=True)

        # ── Variación vs mes anterior (para chips de tendencia en los KPIs) ────
        # Se reutiliza la serie `tendencia` ya calculada arriba (no requiere
        # queries adicionales). Compara el último mes cerrado contra el previo.
        def _mom(campo):
            vals = [m[campo] for m in tendencia]
            if len(vals) < 2 or not vals[-2]:
                return None
            return round((vals[-1] - vals[-2]) / vals[-2] * 100, 1)

        mom = {"confirmados": _mom("confirmados"), "cotizaciones": _mom("cotizaciones")}

        return {
            "pedidos": {
                "total":            len(todos),
                "confirmados":      len(confirmados),
                "cotizaciones":     len(cotizaciones),
                "borrador":         len(borrador),
                "enviadas":         len(enviadas),
                "cancelados":       len(cancelados),
                "kilos_produccion": kilos_produccion,
                "kilos_cotizado":   kilos_cotizado,
                "kilos_entregado":  kilos_entregado,
                "kilos_pendientes": kilos_pendientes,
                "monto_produccion": monto_produccion,
                "monto_cotizado":   monto_cotizado,
                "pct_confirmados":  pct_confirmados,
                "estado_dist":      estado_dist,
                "estado_kg":        estado_kg,
                "top_clientes":     top_clientes,
                "top_pedidos":      top_pedidos,
                "tendencia":        tendencia,
                "detalle":          detalle,
                "por_vendedor":     por_vendedor,
                "mom":              mom,
            },
            "productos": {
                "por_producto": por_producto,
                "por_color":    por_color,
            },
        }
