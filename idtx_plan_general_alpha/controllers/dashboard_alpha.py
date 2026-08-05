import datetime
import logging
import pytz
from collections import defaultdict
from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)

_TEXPLUS_DSN = "DSN=ENBTEX1_DSN;PORT=1433;UID=sistemas;PWD=idtE#21@IRdc95;TDS_Version=7.3"


def _maq_tipo(cod):
    p = (cod or "")[:2].upper()
    if p == "TT" or cod.upper() in ("BIANCA", "CEPILL", "TTHD01", "TTHD02"):
        return "Tintorería"
    if p == "AC":
        return "Acabados"
    if p == "PR":
        return "Preparado"
    if p == "ES":
        return "Estampado"
    return "Otros"


class PlanAlphaDashboard(http.Controller):

    def _get_maquinas_data(self):
        try:
            import pyodbc
            conn = pyodbc.connect(_TEXPLUS_DSN, timeout=5)
            cursor = conn.cursor()

            cursor.execute("""
                SELECT TOP 15
                    c.MaqCod, m.MaqDsc,
                    SUM(CASE WHEN CAST(c.HisProFec AS DATE) = CAST(GETDATE() AS DATE)
                             THEN c.HisProULin ELSE 0 END) AS hoy,
                    SUM(CASE WHEN c.HisProFec >= DATEADD(day, -7, GETDATE())
                             THEN c.HisProULin ELSE 0 END) AS semana
                FROM CHIPRO c
                JOIN MAQUIN m ON m.MaqCod = c.MaqCod AND m.EmprCod = c.EmprCod
                WHERE c.HisProFec >= DATEADD(day, -7, GETDATE())
                  AND m.MaqTip = 'E'
                GROUP BY c.MaqCod, m.MaqDsc
                HAVING SUM(CASE WHEN c.HisProFec >= DATEADD(day, -7, GETDATE())
                                THEN c.HisProULin ELSE 0 END) > 0
                ORDER BY hoy DESC, semana DESC
            """)
            top_maquinas = []
            for row in cursor.fetchall():
                cod  = str(row[0]).strip()
                desc = str(row[1]).strip()
                top_maquinas.append({
                    "cod": cod, "desc": desc,
                    "hoy": int(row[2] or 0), "semana": int(row[3] or 0),
                    "tipo": _maq_tipo(cod),
                })

            cursor.execute("""
                SELECT
                    CAST(c.HisProFec AS DATE) AS dia,
                    SUM(CASE WHEN LEFT(c.MaqCod,2)='TT' OR c.MaqCod IN ('BIANCA','CEPILL')
                             THEN c.HisProULin ELSE 0 END) AS tintoreria,
                    SUM(CASE WHEN LEFT(c.MaqCod,2)='AC' THEN c.HisProULin ELSE 0 END) AS acabados,
                    SUM(CASE WHEN LEFT(c.MaqCod,2)='PR' THEN c.HisProULin ELSE 0 END) AS preparado,
                    SUM(CASE WHEN LEFT(c.MaqCod,2)='ES' THEN c.HisProULin ELSE 0 END) AS estampado
                FROM CHIPRO c
                WHERE c.HisProFec >= DATEADD(day, -7, GETDATE())
                  AND c.HisProFec <= GETDATE()
                GROUP BY CAST(c.HisProFec AS DATE)
                ORDER BY dia
            """)
            tendencia_maq = [
                {
                    "dia": str(row[0])[:10],
                    "tintoreria": int(row[1] or 0),
                    "acabados":   int(row[2] or 0),
                    "preparado":  int(row[3] or 0),
                    "estampado":  int(row[4] or 0),
                }
                for row in cursor.fetchall()
            ]
            conn.close()
            return {"top_maquinas": top_maquinas, "tendencia_maq": tendencia_maq, "disponible": True}
        except Exception as e:
            _logger.warning("Plan Alpha Dashboard: TEXPLUS no disponible — %s", e)
            return {"top_maquinas": [], "tendencia_maq": [], "disponible": False}

    @http.route(
        "/idtx_plan_alpha/workcenters",
        type="jsonrpc",
        auth="user",
        methods=["POST"],
    )
    def alpha_workcenters(self):
        """Return all mrp.workcenter that have active equipment, with machine count."""
        env = request.env
        Equipment = env["maintenance.equipment"].sudo()
        Workcenter = env["mrp.workcenter"].sudo()

        if "workcenter_id" in Equipment._fields:
            equipments = Equipment.search([("active", "=", True)])
            wc_counts = {}
            for eq in equipments:
                if eq.workcenter_id:
                    wc_counts[eq.workcenter_id.id] = wc_counts.get(eq.workcenter_id.id, 0) + 1
            wcs = Workcenter.browse(list(wc_counts)).filtered(lambda w: w.active).sorted("name")
            workcenters = [{"name": wc.name, "count": wc_counts.get(wc.id, 0)} for wc in wcs]
        else:
            # Fallback: fixed list
            workcenters = [
                {"name": "TINTORERIA", "count": 0},
                {"name": "TEJEDURIA",  "count": 0},
            ]
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
        domain = [("active", "=", True)]

        if "workcenter_id" in Equipment._fields:
            wc = env["mrp.workcenter"].sudo().search([("name", "=", workcenter)], limit=1)
            if wc:
                domain.append(("workcenter_id", "=", wc.id))
            else:
                return {"machines": [], "workcenter": workcenter}
        else:
            KEYWORDS = {
                "TEJEDURIA":  ["TEJED", "TEJID"],
                "TINTORERIA": ["TINTOR", "TINTE"],
            }
            kws = KEYWORDS.get(workcenter.upper(), [])
            if not kws:
                return {"machines": [], "workcenter": workcenter}
            Dept = env["hr.department"].sudo()
            dept_ids = []
            for kw in kws:
                dept_ids += Dept.search([("name", "ilike", kw)]).ids
            if not dept_ids:
                return {"machines": [], "workcenter": workcenter}
            domain.append(("department_id", "in", dept_ids))

        equipments = Equipment.search(domain, order="name asc")

        GRID_COLS_OLD = 20
        GRID_COLS_NEW = 24

        Layout = env["idtx.alpha.floor.layout"].sudo()
        existing = Layout.search([("workcenter", "=", workcenter)])
        layout_map = {l.equipment_id.id: l.slot_index for l in existing}
        occupied = set(layout_map.values())

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
    def save_floor_position(self, equipment_id=None, workcenter=None, slot_index=None):
        """Persist a machine's grid slot position."""
        if not equipment_id or not workcenter or slot_index is None:
            return {"ok": False}
        env = request.env
        Layout = env["idtx.alpha.floor.layout"].sudo()
        existing = Layout.search(
            [("equipment_id", "=", equipment_id), ("workcenter", "=", workcenter)], limit=1
        )
        if existing:
            existing.slot_index = slot_index
        else:
            Layout.create({"equipment_id": equipment_id, "workcenter": workcenter, "slot_index": slot_index})
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
        vend = defaultdict(lambda: {"cotizaciones": 0, "kg_cotizado": 0.0,
                                     "confirmados": 0, "kg_confirmado": 0.0})
        for o in cotizaciones:
            v = vend[o.user_id.name or "Sin vendedor"]
            v["cotizaciones"] += 1
            v["kg_cotizado"] += _kg(o)
        for o in confirmados:
            v = vend[o.user_id.name or "Sin vendedor"]
            v["confirmados"] += 1
            v["kg_confirmado"] += _kg(o)
        por_vendedor = sorted(
            [{"vendedor": k,
              "cotizaciones": v["cotizaciones"], "kg_cotizado": round(v["kg_cotizado"], 1),
              "confirmados": v["confirmados"], "kg_confirmado": round(v["kg_confirmado"], 1)}
             for k, v in vend.items()],
            key=lambda x: x["kg_cotizado"] + x["kg_confirmado"], reverse=True)

        maquinas = self._get_maquinas_data()

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
            },
            "productos": {
                "por_producto": por_producto,
                "por_color":    por_color,
            },
            "maquinas": maquinas,
        }
