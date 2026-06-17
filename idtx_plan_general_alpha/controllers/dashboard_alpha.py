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
