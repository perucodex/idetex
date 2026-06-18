# -*- coding: utf-8 -*-
import datetime
from odoo import http
from odoo.http import request


class PlanGeneralDashboard(http.Controller):

    @http.route(
        "/idtx_plan_general/dashboard_data",
        type="jsonrpc",
        auth="user",
        methods=["POST"],
    )
    def dashboard_data(self):
        env = request.env
        today = datetime.date.today()
        in_7_days = today + datetime.timedelta(days=7)

        # ── Pedidos ─────────────────────────────────────────────────────────
        Pedido = env["control.pedido"].sudo()

        activos = Pedido.search([("state", "in", ["on", "de"])])
        on_time_recs = activos.filtered(lambda p: p.state == "on")
        delayed_recs = activos.filtered(lambda p: p.state == "de")

        done_recs = Pedido.search([("state", "=", "do")])
        settled_count = Pedido.search_count([("state", "=", "se")])

        kilos_total = sum(activos.mapped("total_weight"))
        kilos_done = round(sum(done_recs.mapped("total_weight")), 2)

        # Promedio días de retraso
        avg_delay = 0.0
        if delayed_recs:
            avg_delay = round(
                sum(p.num_days or 0 for p in delayed_recs) / len(delayed_recs), 1
            )

        # Top 10 retrasados
        top_delayed = delayed_recs.sorted(key=lambda p: p.num_days, reverse=True)[:10]
        top_delayed_data = [
            {
                "num": p.numordped or "",
                "days": p.num_days or 0,
                "customer": p.customer or "",
                "area": p.area or "",
            }
            for p in top_delayed
        ]

        # Próximos a vencer en 7 días
        proximos = activos.filtered(
            lambda p: p.wish_date and today <= p.wish_date <= in_7_days
        ).sorted(key=lambda p: p.wish_date)
        proximos_data = [
            {
                "num": p.numordped or "",
                "customer": p.customer or "",
                "wish_date": str(p.wish_date) if p.wish_date else "",
                "days": (p.wish_date - today).days if p.wish_date else 0,
                "state": p.state or "",
                "area": p.area or "",
            }
            for p in proximos
        ]

        # Top clientes por kilos (activos)
        customer_map = {}
        for p in activos:
            cust = (p.customer or "Sin Cliente").strip()
            if cust not in customer_map:
                customer_map[cust] = {"count": 0, "kilos": 0.0, "delayed": 0}
            customer_map[cust]["count"] += 1
            customer_map[cust]["kilos"] += p.total_weight or 0.0
            if p.state == "de":
                customer_map[cust]["delayed"] += 1

        top_clientes = sorted(
            [
                {
                    "customer": k,
                    "count": v["count"],
                    "kilos": round(v["kilos"], 2),
                    "delayed": v["delayed"],
                }
                for k, v in customer_map.items()
            ],
            key=lambda x: x["kilos"],
            reverse=True,
        )[:10]

        total_clientes = len(customer_map)

        # Clientes con pedidos retrasados
        clientes_retrasados = len(
            set((p.customer or "Sin Cliente").strip() for p in delayed_recs)
        )

        # Distribución por estado (todos los pedidos históricos)
        all_pedidos_count = Pedido.search_count([])
        estado_dist = [
            {"estado": "A Tiempo",  "key": "on", "count": len(on_time_recs),    "color": "#10b981"},
            {"estado": "Retrasados","key": "de", "count": len(delayed_recs),    "color": "#ef4444"},
            {"estado": "Terminados","key": "do", "count": len(done_recs),       "color": "#3b82f6"},
            {"estado": "Liquidados","key": "se", "count": settled_count,        "color": "#94a3b8"},
        ]

        # ── Partidas ─────────────────────────────────────────────────────────
        Line = env["control.pedido.line"].sudo()
        activas_lines = Line.search([("state", "=", "active")])

        sin_avance_count = len(
            activas_lines.filtered(
                lambda l: (l.process or "").strip().upper() == "SIN AVANCE"
            )
        )

        # Por área (top 8)
        area_map = {}
        for line in activas_lines:
            area_key = (line.area or "SIN ÁREA").strip()
            if area_key not in area_map:
                area_map[area_key] = {"count": 0, "kilos": 0.0}
            area_map[area_key]["count"] += 1
            area_map[area_key]["kilos"] += line.kilograms or 0.0

        por_area = sorted(
            [
                {"area": k, "count": v["count"], "kilos": round(v["kilos"], 2)}
                for k, v in area_map.items()
            ],
            key=lambda x: x["kilos"],
            reverse=True,
        )[:8]

        # Por proceso (top 12)
        proceso_map = {}
        for line in activas_lines:
            proc = (line.process or "Sin Proceso").strip() or "Sin Proceso"
            if proc not in proceso_map:
                proceso_map[proc] = {"count": 0, "kilos": 0.0}
            proceso_map[proc]["count"] += 1
            proceso_map[proc]["kilos"] += line.kilograms or 0.0

        por_proceso = sorted(
            [
                {"proceso": k, "count": v["count"], "kilos": round(v["kilos"], 2)}
                for k, v in proceso_map.items()
            ],
            key=lambda x: x["count"],
            reverse=True,
        )[:12]

        return {
            "pedidos": {
                "total_activos": len(activos),
                "on_time": len(on_time_recs),
                "delayed": len(delayed_recs),
                "done": len(done_recs),
                "settled": settled_count,
                "kilos_total": round(kilos_total, 2),
                "kilos_done": kilos_done,
                "avg_delay": avg_delay,
                "total_clientes": total_clientes,
                "clientes_retrasados": clientes_retrasados,
                "all_count": all_pedidos_count,
                "top_delayed": top_delayed_data,
                "proximos_vencer": proximos_data,
                "top_clientes": top_clientes,
                "estado_dist": estado_dist,
            },
            "partidas": {
                "total_activas": len(activas_lines),
                "sin_avance": sin_avance_count,
                "por_area": por_area,
                "por_proceso": por_proceso,
            },
        }

    @http.route(
        "/idtx_plan_general/programacion_data",
        type="jsonrpc",
        auth="user",
        methods=["POST"],
    )
    def programacion_data(self, area=None):
        env = request.env

        # Keywords para buscar el nombre del departamento en hr.department
        AREA_KEYWORDS = {
            "hilanderia": ["HILAND"],
            "tejeduria":  ["TEJED", "TEJID"],
            "tintoreria": ["TINTOR", "TINTE"],
            "estampado":  ["ESTAMP"],
            "acabado":    ["ACAB"],
            "calidad":    ["CALID", "QC", "QA"],
        }

        keywords = AREA_KEYWORDS.get(area or "", [])
        if not keywords:
            return {"machines": [], "area": area}

        # Buscar departamentos cuyo nombre contenga alguna de las palabras clave
        Dept = env["hr.department"].sudo()
        dept_ids = []
        for kw in keywords:
            dept_ids += Dept.search([("name", "ilike", kw)]).ids

        Equipment = env["maintenance.equipment"].sudo()
        if dept_ids:
            domain = [("department_id", "in", dept_ids), ("active", "=", True)]
        else:
            # Si no hay departamentos configurados devolvemos vacío
            return {"machines": [], "area": area}

        equipments = Equipment.search(domain, order="name asc")

        # ── Posiciones de la cuadrícula ──────────────────────────────────────
        Layout = env["idtx.machine.layout"].sudo()
        existing = Layout.search([("area", "=", area)])
        layout_map = {l.equipment_id.id: l.slot_index for l in existing}
        occupied_slots = set(layout_map.values())

        # Auto-asignar slots a máquinas que no tienen posición guardada
        next_slot = 0
        to_create = []
        for eq in equipments:
            if eq.id not in layout_map:
                while next_slot in occupied_slots:
                    next_slot += 1
                layout_map[eq.id] = next_slot
                occupied_slots.add(next_slot)
                to_create.append({"equipment_id": eq.id, "area": area, "slot_index": next_slot})
                next_slot += 1
        if to_create:
            Layout.create(to_create)

        machines = []
        for eq in equipments:
            machines.append({
                "id":         eq.id,
                "name":       eq.name or "",
                "code":       eq.code or "",
                "category":   eq.category_id.name if eq.category_id else "",
                "department": eq.department_id.name if eq.department_id else "",
                "model":      eq.model or "",
                "serial":     eq.serial_no or "",
                "enabled":    bool(eq.enabled) if hasattr(eq, "enabled") else True,
                "oos":        bool(eq.oos)     if hasattr(eq, "oos")     else False,
                "slot_index": layout_map.get(eq.id, 0),
            })

        return {"machines": machines, "area": area}

    @http.route(
        "/idtx_plan_general/save_machine_position",
        type="jsonrpc",
        auth="user",
        methods=["POST"],
    )
    def save_machine_position(self, equipment_id=None, area=None, slot_index=None):
        if not equipment_id or not area or slot_index is None:
            return {"ok": False}
        env = request.env
        Layout = env["idtx.machine.layout"].sudo()
        existing = Layout.search(
            [("equipment_id", "=", equipment_id), ("area", "=", area)], limit=1
        )
        if existing:
            existing.slot_index = slot_index
        else:
            Layout.create({"equipment_id": equipment_id, "area": area, "slot_index": slot_index})
        return {"ok": True}

    @http.route(
        "/idtx_plan_general/planning_data",
        type="jsonrpc",
        auth="user",
        methods=["POST"],
    )
    def planning_data(self):
        env = request.env
        today = datetime.date.today()

        Pedido = env["control.pedido"].sudo()
        pedidos = Pedido.search(
            [("state", "in", ["on", "de", "do"]), ("fecha", "!=", False)],
            order="wish_date asc",
        )

        rows = []
        for p in pedidos:
            end = p.wish_date or (p.fecha + datetime.timedelta(days=30))
            rows.append({
                "id": p.id,
                "num": p.numordped or "—",
                "customer": (p.customer or "Sin Cliente").strip(),
                "area": (p.area or "SIN ÁREA").strip(),
                "state": p.state or "on",
                "start": str(p.fecha),
                "end": str(end),
                "weight": round(p.total_weight or 0, 1),
                "num_days": p.num_days or 0,
            })

        return {"rows": rows, "today": str(today)}
