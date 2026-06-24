# -*- coding: utf-8 -*-
import datetime
import logging
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

    # ── TEXPLUS: producción de máquinas ───────────────────────────────────────
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
        """Return machines for a workcenter with their grid slot positions."""
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

        # ── Grid slot positions ──────────────────────────────────────────────
        GRID_COLS_OLD = 20
        GRID_COLS_NEW = 24

        Layout = env["idtx.alpha.floor.layout"].sudo()
        existing = Layout.search([("workcenter", "=", workcenter)])
        layout_map = {l.equipment_id.id: l.slot_index for l in existing}
        occupied = set(layout_map.values())

        # One-time import from old idtx.machine.layout (if exists)
        # Sort by old slot_index to preserve physical order, then assign
        # sequential slots without gaps.
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
        """Devuelve datos completos de una máquina y sus pedidos activos en su workcenter."""
        if not equipment_id:
            return {"machine": None, "pedidos": []}
        env = request.env
        eq = env["maintenance.equipment"].sudo().browse(int(equipment_id))
        if not eq.exists():
            return {"machine": None, "pedidos": []}

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

        # Pedidos activos cuyo proceso o siguiente proceso apunta al workcenter de la máquina
        pedidos = []
        wc_name = machine["workcenter"]
        if wc_name and "control.pedido.line" in env.registry.models:
            try:
                Line = env["control.pedido.line"].sudo()
                lines = Line.search([
                    ("state", "=", "active"),
                    "|",
                    ("area", "ilike", wc_name),
                    ("process", "ilike", wc_name),
                ], limit=30, order="wish_date asc")
                for l in lines:
                    pedidos.append({
                        "id":         l.id,
                        "batch":      l.batch or "",
                        "process":    l.process or "",
                        "customer":   (l.customer or "")[:30],
                        "kilograms":  round(l.kilograms or 0, 1),
                        "area":       l.area or "",
                        "wish_date":  str(l.wish_date) if l.wish_date else "",
                        "num_days":   l.num_days or 0,
                    })
            except Exception:
                _logger.warning("machine_detail: error cargando pedidos", exc_info=True)

        return {"machine": machine, "pedidos": pedidos}

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
        env = request.env
        today = datetime.date.today()
        in_7_days = today + datetime.timedelta(days=7)
        in_14_days = today + datetime.timedelta(days=14)

        Pedido = env["control.pedido"].sudo()
        Line = env["control.pedido.line"].sudo()

        # ── Pedidos activos ───────────────────────────────────────────────────
        activos = Pedido.search([("state", "in", ["on", "de"])])
        on_time_recs  = activos.filtered(lambda p: p.state == "on")
        delayed_recs  = activos.filtered(lambda p: p.state == "de")
        done_recs     = Pedido.search([("state", "=", "do")])
        settled_count = Pedido.search_count([("state", "=", "se")])

        kilos_activos = round(sum(activos.mapped("total_weight")), 1)
        kilos_done    = round(sum(done_recs.mapped("total_weight")), 1)

        proximos_7d_recs = activos.filtered(
            lambda p: p.wish_date and today <= p.wish_date <= in_7_days
        )
        proximos_14d_recs = activos.filtered(
            lambda p: p.wish_date and today <= p.wish_date <= in_14_days
        ).sorted(key=lambda p: p.wish_date)

        # ── Estados (distribución) ────────────────────────────────────────────
        estado_dist = [
            {"estado": "A Tiempo",   "key": "on", "count": len(on_time_recs),  "color": "#22c55e"},
            {"estado": "Demorados",  "key": "de", "count": len(delayed_recs),  "color": "#ef4444"},
            {"estado": "Terminados", "key": "do", "count": len(done_recs),     "color": "#3b82f6"},
            {"estado": "Liquidados", "key": "se", "count": settled_count,      "color": "#94a3b8"},
        ]

        # ── Top Clientes por kg ───────────────────────────────────────────────
        customer_map = defaultdict(lambda: {"kilos": 0.0, "count": 0})
        for p in activos:
            k = (p.customer or "Sin Cliente").strip()
            customer_map[k]["kilos"] += p.total_weight or 0.0
            customer_map[k]["count"] += 1

        top_clientes = sorted(
            [{"customer": k, "kilos": round(v["kilos"], 1), "count": v["count"]}
             for k, v in customer_map.items()],
            key=lambda x: x["kilos"], reverse=True
        )[:12]

        # ── Top Retrasados ────────────────────────────────────────────────────
        top_delayed = sorted(
            [{"num": p.numordped or "", "customer": (p.customer or "").strip(),
              "days": p.num_days or 0, "area": (p.area or "").strip()}
             for p in delayed_recs],
            key=lambda x: x["days"], reverse=True
        )[:10]

        # ── Próximos a vencer (14d) ───────────────────────────────────────────
        proximos_vencer = [
            {"num": p.numordped or "",
             "customer": (p.customer or "").strip()[:25],
             "days_left": (p.wish_date - today).days if p.wish_date else 0,
             "state": p.state}
            for p in proximos_14d_recs
        ][:12]

        # ── Partidas ──────────────────────────────────────────────────────────
        activas_lines = Line.search([("state", "=", "active")])
        if not activas_lines:
            activas_lines = Line.search([])  # fallback: mostrar todas

        area_map = defaultdict(lambda: {"kilos": 0.0, "count": 0})
        proceso_map = defaultdict(lambda: {"kilos": 0.0, "count": 0})
        for l in activas_lines:
            a = (l.area or "SIN ÁREA").strip()
            area_map[a]["kilos"] += l.kilograms or 0.0
            area_map[a]["count"] += 1
            proc = (l.process or "Sin Proceso").strip() or "Sin Proceso"
            proceso_map[proc]["kilos"] += l.kilograms or 0.0
            proceso_map[proc]["count"] += 1

        por_area = sorted(
            [{"area": k, "kilos": round(v["kilos"], 1), "count": v["count"]}
             for k, v in area_map.items()],
            key=lambda x: x["kilos"], reverse=True
        )[:10]

        por_proceso = sorted(
            [{"proceso": k, "kilos": round(v["kilos"], 1), "count": v["count"]}
             for k, v in proceso_map.items()],
            key=lambda x: x["count"], reverse=True
        )[:14]

        # ── Próximas 4 semanas ───────────────────────────────────────────────
        proximas_semanas = []
        for i in range(4):
            w_start = today + datetime.timedelta(days=i * 7)
            w_end   = today + datetime.timedelta(days=(i + 1) * 7)
            label   = "Esta semana" if i == 0 else f"Semana {i + 1}"
            count   = len(activos.filtered(
                lambda p, s=w_start, e=w_end: p.wish_date and s <= p.wish_date < e
            ))
            proximas_semanas.append({"label": label, "count": count})

        pct_on_time = round(len(on_time_recs) / max(len(activos), 1) * 100, 1) if activos else 0.0
        avg_delay   = round(
            sum(r.num_days or 0 for r in delayed_recs) / max(len(delayed_recs), 1), 1
        ) if delayed_recs else 0.0

        # ── Tendencia mensual (últimos 6 meses) ───────────────────────────────
        six_months_ago = today - datetime.timedelta(days=180)
        recientes = Pedido.search([("fecha", ">=", six_months_ago)])

        monthly = defaultdict(lambda: {"on": 0, "de": 0, "do": 0})
        for p in recientes:
            if p.fecha:
                key = p.fecha.strftime("%b %Y")
                monthly[key][p.state] = monthly[key].get(p.state, 0) + 1

        # Ordenar meses cronológicamente
        months_order = []
        d = datetime.date(six_months_ago.year, six_months_ago.month, 1)
        while d <= today:
            months_order.append(d.strftime("%b %Y"))
            if d.month == 12:
                d = d.replace(year=d.year + 1, month=1)
            else:
                d = d.replace(month=d.month + 1)

        tendencia = [
            {"mes": m, "on": monthly[m]["on"], "de": monthly[m]["de"], "do": monthly[m]["do"]}
            for m in months_order
        ]

        maquinas = self._get_maquinas_data()

        return {
            "pedidos": {
                "total_activos":       len(activos),
                "on_time":             len(on_time_recs),
                "delayed":             len(delayed_recs),
                "done":                len(done_recs),
                "settled":             settled_count,
                "kilos_activos":       kilos_activos,
                "kilos_done":          kilos_done,
                "proximos_7d":         len(proximos_7d_recs),
                "estado_dist":         estado_dist,
                "top_clientes":        top_clientes,
                "top_delayed":         top_delayed,
                "proximos_vencer":     proximos_vencer,
                "tendencia":           tendencia,
                "pct_on_time":         pct_on_time,
                "avg_delay":           avg_delay,
                "proximas_semanas":    proximas_semanas,
            },
            "partidas": {
                "total_activas": len(activas_lines),
                "por_area":      por_area,
                "por_proceso":   por_proceso,
            },
            "maquinas": maquinas,
        }
