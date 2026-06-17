/** @odoo-module **/

import { Component, useState, onMounted, onWillUnmount, useRef } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { rpc } from "@web/core/network/rpc";
import { cookie } from "@web/core/browser/cookie";

// ── Palette ──────────────────────────────────────────────────────────────────
const C = {
    indigo: "#6366f1", green: "#22c55e", red: "#ef4444",
    amber:  "#f59e0b", cyan:  "#06b6d4", purple: "#8b5cf6",
    blue:   "#3b82f6", slate: "#94a3b8", teal:   "#14b8a6",
    orange: "#f97316", pink:  "#ec4899",
};

const PALETTE = [
    C.indigo, C.cyan, C.teal, C.amber, C.pink,
    C.green, C.purple, C.orange, C.blue, C.red, C.slate,
    "#a78bfa", "#34d399", "#fbbf24",
];

// Machine-type color map
const MAQ_COLORS = {
    "Tintorería": C.blue,
    "Acabados":   C.teal,
    "Preparado":  C.amber,
    "Estampado":  C.pink,
    "Otros":      C.slate,
};

const FONT = "'Inter','Segoe UI',system-ui,sans-serif";

// ── Dark-aware base config ────────────────────────────────────────────────────
function base(dk) {
    return {
        chart: {
            toolbar: { show: false }, fontFamily: FONT,
            background: "transparent",
            foreColor: dk ? "#94a3b8" : "#64748b",
            animations: { enabled: true, easing: "easeinout", speed: 700,
                          animateGradually: { enabled: true, delay: 100 } },
        },
        grid: { borderColor: dk ? "#334155" : "#f1f5f9", strokeDashArray: 3, padding: { right: 12 } },
        tooltip: { theme: dk ? "dark" : "light", style: { fontSize: "12px", fontFamily: FONT } },
    };
}

function axs(dk, sz = "11px", col = null) {
    return { style: { fontSize: sz, fontFamily: FONT, colors: col || (dk ? "#94a3b8" : "#64748b") } };
}

function lgd(dk) {
    return {
        fontSize: "12px", fontFamily: FONT,
        markers: { size: 6, shape: "circle" },
        labels: { colors: dk ? "#cbd5e1" : "#475569" },
    };
}

function fmtKg(v) {
    const n = Number(v);
    return n >= 1000 ? (n / 1000).toFixed(1) + "k" : String(Math.round(n));
}

// ── Component ──────────────────────────────────────────────────────────────────
export class DashboardAlpha extends Component {
    static template = "idtx_plan_general_alpha.DashboardAlpha";
    static props = ["*"];

    setup() {
        this.state = useState({ loading: true, error: null, data: null });
        this._charts = {};

        this.rScroll = useRef("scroll");
        this.r1 = useRef("c1");   // donut estados
        this.r2 = useRef("c2");   // gauge speedometer
        this.r3 = useRef("c3");   // mixed tendencia
        this.r4 = useRef("c4");   // hbar clientes
        this.r5 = useRef("c5");   // hbar retrasados
        this.r6 = useRef("c6");   // bar area
        this.r7 = useRef("c7");   // hbar proceso
        this.r8 = useRef("c8");   // bar semanas
        this.r9 = useRef("c9");   // hbar máquinas activas hoy
        this.r10 = useRef("c10"); // grouped bar tendencia máquinas

        onMounted(async () => { await this._load(); });
        onWillUnmount(() => {
            Object.values(this._charts).forEach(c => c && c.destroy());
            this._charts = {};
        });
    }

    // ── Theme detection — usa la cookie oficial de Odoo ───────────────────────
    _isDark() {
        return cookie.get("color_scheme") === "dark";
    }

    // ── Load data ─────────────────────────────────────────────────────────────
    async _load() {
        try {
            const data = await rpc("/idtx_plan_alpha/dashboard_data");
            this.state.data = data;
            this.state.loading = false;
            setTimeout(() => {
                this._renderAll();
                this._countUp();
            }, 150);
        } catch (e) {
            this.state.error = "No se pudieron cargar los datos del dashboard.";
            this.state.loading = false;
        }
    }

    // ── Render all charts ─────────────────────────────────────────────────────
    _renderAll() {
        Object.values(this._charts).forEach(c => c && c.destroy());
        this._charts = {};
        const d = this.state.data;
        if (!d || !window.ApexCharts) return;
        const dk = this._isDark();
        this._chartDonut(d, dk);
        this._chartGauge(d, dk);
        this._chartTendencia(d, dk);
        this._chartClientes(d, dk);
        this._chartRetrasados(d, dk);
        this._chartArea(d, dk);
        this._chartProceso(d, dk);
        this._chartSemanas(d, dk);
        if (d.maquinas && d.maquinas.disponible) {
            this._chartMaquinas(d, dk);
            this._chartTendenciaMaq(d, dk);
        }
    }

    // ── Count-up animation ────────────────────────────────────────────────────
    _countUp() {
        const scroll = this.rScroll.el;
        if (!scroll) return;
        scroll.querySelectorAll("[data-cnt]").forEach(el => {
            const target = parseFloat(el.dataset.cnt);
            const isKg   = el.dataset.kg === "1";
            if (isNaN(target) || target <= 0) return;
            const dur = 1400, t0 = performance.now();
            const tick = now => {
                const p = Math.min((now - t0) / dur, 1);
                const e = 1 - Math.pow(1 - p, 4);
                const v = Math.round(target * e);
                el.textContent = isKg
                    ? (v >= 1000 ? (v / 1000).toFixed(1) + "k kg" : v + " kg")
                    : v.toLocaleString("es-PE");
                if (p < 1) requestAnimationFrame(tick);
            };
            requestAnimationFrame(tick);
        });
    }

    // ── 1 · Donut estados ─────────────────────────────────────────────────────
    _chartDonut(d, dk) {
        const el = this.r1.el; if (!el) return;
        const dist  = d.pedidos.estado_dist;
        const total = d.pedidos.total_activos + d.pedidos.done + d.pedidos.settled;
        const tC = dk ? "#94a3b8" : "#64748b";
        const vC = dk ? "#f1f5f9" : "#0f172a";
        const sC = dk ? "#1e293b" : "#ffffff";
        const c = new window.ApexCharts(el, {
            ...base(dk),
            chart:  { ...base(dk).chart, type: "donut", height: 280 },
            series: dist.map(e => e.count),
            labels: dist.map(e => e.estado),
            colors: dk
                ? ["#34d399", "#f87171", "#818cf8", "#94a3b8"]
                : [C.green, C.red, C.blue, C.slate],
            plotOptions: { pie: { donut: {
                size: "72%",
                labels: { show: true,
                    name:  { fontSize: "11px", fontFamily: FONT, color: tC, offsetY: 5 },
                    value: { fontSize: "24px", fontWeight: 800, fontFamily: FONT, color: vC, offsetY: -4 },
                    total: { show: true, label: "Total", color: tC, fontSize: "11px",
                             fontFamily: FONT, fontWeight: 600,
                             formatter: () => total.toLocaleString() },
                },
            } } },
            legend: { position: "bottom", ...lgd(dk), itemMargin: { horizontal: 8 } },
            dataLabels: { enabled: false },
            stroke: { width: 2, colors: [sC] },
        });
        this._charts.donut = c; c.render();
    }

    // ── 2 · Gauge speedometer (semi-circle) ───────────────────────────────────
    _chartGauge(d, dk) {
        const el = this.r2.el; if (!el) return;
        const pctOn  = d.pedidos.pct_on_time || 0;
        const color  = pctOn >= 80 ? C.green : pctOn >= 60 ? C.amber : C.red;
        const colorG = pctOn >= 80 ? "#86efac" : pctOn >= 60 ? "#fcd34d" : "#fca5a5";
        const trackC = dk ? "#334155" : "#f1f5f9";
        const tC     = dk ? "#94a3b8" : "#64748b";
        const vC     = dk ? "#f1f5f9" : "#0f172a";
        const c = new window.ApexCharts(el, {
            ...base(dk),
            chart: { ...base(dk).chart, type: "radialBar", height: 280 },
            series: [pctOn],
            colors: [color],
            plotOptions: {
                radialBar: {
                    startAngle: -135, endAngle: 135,
                    hollow: {
                        size: "62%", background: "transparent",
                        dropShadow: { enabled: dk, top: 2, blur: 6, color: "#000", opacity: 0.2 },
                    },
                    track: { background: trackC, strokeWidth: "100%", margin: 0 },
                    dataLabels: {
                        name: {
                            show: true, offsetY: -10,
                            fontSize: "11px", fontFamily: FONT, fontWeight: 600, color: tC,
                            formatter: () => "Cumplimiento",
                        },
                        value: {
                            offsetY: 14, fontSize: "30px", fontWeight: 800,
                            fontFamily: FONT, color: vC,
                            formatter: v => parseFloat(v).toFixed(1) + "%",
                        },
                    },
                },
            },
            fill: {
                type: "gradient",
                gradient: { shade: "dark", type: "horizontal", gradientToColors: [colorG], stops: [0, 100] },
            },
            stroke: { lineCap: "round" },
        });
        this._charts.gauge = c; c.render();
    }

    // ── 3 · Mixed chart: columnas A Tiempo/Demorados + línea Terminados ───────
    _chartTendencia(d, dk) {
        const el    = this.r3.el; if (!el) return;
        const items = d.pedidos.tendencia;
        const c = new window.ApexCharts(el, {
            ...base(dk),
            chart: { ...base(dk).chart, type: "line", height: 280 },
            series: [
                { name: "A Tiempo",   type: "column", data: items.map(t => t.on) },
                { name: "Demorados",  type: "column", data: items.map(t => t.de) },
                { name: "Terminados", type: "line",   data: items.map(t => t.do) },
            ],
            colors: [C.green, C.red, C.blue],
            stroke: { width: [0, 0, 2.5], curve: "smooth" },
            fill: { opacity: [0.85, 0.85, 1] },
            markers: { size: [0, 0, 4], strokeColors: dk ? "#1e293b" : "#ffffff", strokeWidth: 2 },
            xaxis: {
                categories: items.map(t => t.mes),
                ...axs(dk), axisBorder: { show: false }, axisTicks: { show: false },
            },
            yaxis: { labels: axs(dk) },
            plotOptions: { bar: { columnWidth: "55%", borderRadius: 4, borderRadiusApplication: "end" } },
            legend: { position: "top", horizontalAlign: "right", ...lgd(dk) },
            dataLabels: { enabled: false },
            tooltip: { shared: true, intersect: false },
        });
        this._charts.tendencia = c; c.render();
    }

    // ── 4 · HBar top clientes ─────────────────────────────────────────────────
    _chartClientes(d, dk) {
        const el    = this.r4.el; if (!el) return;
        const items = d.pedidos.top_clientes.slice(0, 8);
        const lblC  = dk ? "#cbd5e1" : "#374151";
        const c = new window.ApexCharts(el, {
            ...base(dk),
            chart: { ...base(dk).chart, type: "bar", height: 320 },
            plotOptions: { bar: { horizontal: true, barHeight: "60%",
                                  borderRadius: 5, borderRadiusApplication: "end",
                                  distributed: true } },
            series: [{ name: "Kg", data: items.map(i => i.kilos) }],
            xaxis: {
                categories: items.map(i => i.customer.substring(0, 26)),
                labels: { ...axs(dk), formatter: v => fmtKg(Number(v)) },
                axisBorder: { show: false }, axisTicks: { show: false },
            },
            yaxis: { labels: { style: { fontSize: "11px", fontFamily: FONT, colors: lblC }, maxWidth: 170 } },
            colors: PALETTE.slice(0, items.length),
            legend: { show: false },
            dataLabels: { enabled: true, textAnchor: "start",
                          style: { fontSize: "11px", fontFamily: FONT, colors: [lblC], fontWeight: 500 },
                          formatter: v => fmtKg(v) + " kg", offsetX: 6 },
            tooltip: { y: { formatter: v => v.toLocaleString() + " kg" } },
        });
        this._charts.clientes = c; c.render();
    }

    // ── 5 · HBar retrasados con línea de referencia 30d ──────────────────────
    _chartRetrasados(d, dk) {
        const el    = this.r5.el; if (!el) return;
        const items = d.pedidos.top_delayed.slice(0, 8);
        if (!items.length) return;
        const lblC   = dk ? "#cbd5e1" : "#374151";
        const bg     = dk ? "#1e293b" : "#ffffff";
        const fg     = dk ? "#f1f5f9" : "#0f172a";
        const colors = items.map(r => r.days > 150 ? C.red : r.days > 80 ? C.amber : C.slate);
        const maxVal = Math.max(...items.map(r => r.days), 30);
        const c = new window.ApexCharts(el, {
            ...base(dk),
            chart: { ...base(dk).chart, type: "bar", height: 320 },
            plotOptions: { bar: { horizontal: true, barHeight: "60%",
                                  borderRadius: 5, borderRadiusApplication: "end",
                                  distributed: true } },
            series: [{ name: "Días", data: items.map(r => r.days) }],
            xaxis: {
                categories: items.map(r => (r.num || r.customer).substring(0, 16)),
                labels: axs(dk), axisBorder: { show: false }, axisTicks: { show: false },
                max: Math.ceil(maxVal * 1.12),
            },
            yaxis: { labels: { style: { fontSize: "11px", fontFamily: FONT, colors: lblC } } },
            colors,
            legend: { show: false },
            annotations: {
                xaxis: [{
                    x: 30, borderColor: C.amber, strokeDashArray: 5, borderWidth: 2,
                    label: {
                        text: "30d", position: "bottom",
                        style: { background: C.amber, color: "#fff",
                                 fontSize: "10px", fontFamily: FONT,
                                 padding: { left: 6, right: 6, top: 2, bottom: 2 } },
                    },
                }],
            },
            dataLabels: { enabled: true, textAnchor: "start",
                          style: { fontSize: "11px", fontFamily: FONT, colors: [lblC], fontWeight: 500 },
                          formatter: v => v + "d", offsetX: 6 },
            tooltip: {
                custom: ({ dataPointIndex: i }) => {
                    const r = items[i];
                    return `<div style="padding:10px 14px;font-size:12px;font-family:${FONT};background:${bg};color:${fg};border-radius:8px">
                        <strong>${r.num}</strong> · ${r.customer}<br>
                        <span style="color:${C.red};font-weight:700">${r.days} días de retraso</span>
                        ${r.area ? ` · <em>${r.area}</em>` : ""}
                    </div>`;
                },
            },
        });
        this._charts.retrasados = c; c.render();
    }

    // ── 6 · Bar partidas por área ─────────────────────────────────────────────
    _chartArea(d, dk) {
        const el    = this.r6.el; if (!el) return;
        const items = d.partidas.por_area.slice(0, 10);
        const c = new window.ApexCharts(el, {
            ...base(dk),
            chart: { ...base(dk).chart, type: "bar", height: 280 },
            plotOptions: { bar: { columnWidth: "56%", borderRadius: 7,
                                  borderRadiusApplication: "end", distributed: true } },
            series: [{ name: "Kg", data: items.map(a => a.kilos) }],
            xaxis: {
                categories: items.map(a => a.area.substring(0, 18)),
                labels: { ...axs(dk, "10px"), rotate: -35 },
                axisBorder: { show: false }, axisTicks: { show: false },
            },
            yaxis: { labels: { ...axs(dk, "10px"), formatter: v => fmtKg(v) } },
            colors: PALETTE.slice(0, items.length),
            legend: { show: false },
            dataLabels: { enabled: false },
            tooltip: { y: { formatter: v => v.toLocaleString() + " kg" } },
        });
        this._charts.area = c; c.render();
    }

    // ── 7 · HBar partidas por proceso (gradiente) ─────────────────────────────
    _chartProceso(d, dk) {
        const el    = this.r7.el; if (!el) return;
        const items = d.partidas.por_proceso.slice(0, 10);
        const lblC  = dk ? "#cbd5e1" : "#374151";
        const c = new window.ApexCharts(el, {
            ...base(dk),
            chart: { ...base(dk).chart, type: "bar", height: 340 },
            plotOptions: { bar: { horizontal: true, barHeight: "56%",
                                  borderRadius: 5, borderRadiusApplication: "end" } },
            series: [{ name: "Partidas", data: items.map(p => p.count) }],
            xaxis: {
                categories: items.map(p => p.proceso.substring(0, 24)),
                labels: { ...axs(dk), formatter: v => Math.round(Number(v)) },
                axisBorder: { show: false }, axisTicks: { show: false },
            },
            yaxis: { labels: { style: { fontSize: "11px", fontFamily: FONT, colors: lblC }, maxWidth: 190 } },
            colors: [C.indigo],
            fill: {
                type: "gradient",
                gradient: { shade: dk ? "dark" : "light", type: "horizontal",
                             gradientToColors: [C.cyan], stops: [0, 100] },
            },
            legend: { show: false },
            dataLabels: {
                enabled: true, textAnchor: "start",
                style: { fontSize: "11px", fontFamily: FONT, colors: [lblC], fontWeight: 500 },
                formatter: v => v + " part.", offsetX: 6,
            },
            tooltip: {
                y: { formatter: (v, { dataPointIndex: i }) => {
                    const p = items[i];
                    return `${v} partidas · ${fmtKg(p.kilos)} kg`;
                } },
            },
        });
        this._charts.proceso = c; c.render();
    }

    // ── 8 · Bar semanas próximas ──────────────────────────────────────────────
    _chartSemanas(d, dk) {
        const el    = this.r8.el; if (!el) return;
        const items = d.pedidos.proximas_semanas || [];
        if (!items.length) return;
        const numC = dk ? "#f1f5f9" : "#0f172a";
        const c = new window.ApexCharts(el, {
            ...base(dk),
            chart: { ...base(dk).chart, type: "bar", height: 210 },
            plotOptions: { bar: { columnWidth: "40%", borderRadius: 10,
                                  borderRadiusApplication: "end", distributed: true } },
            series: [{ name: "Pedidos", data: items.map(s => s.count) }],
            xaxis: {
                categories: items.map(s => s.label),
                labels: axs(dk, "12px"), axisBorder: { show: false }, axisTicks: { show: false },
            },
            yaxis: { labels: axs(dk), min: 0 },
            colors: [C.indigo, C.cyan, C.amber, C.red].slice(0, items.length),
            legend: { show: false },
            dataLabels: {
                enabled: true,
                style: { fontSize: "14px", fontFamily: FONT, fontWeight: 800, colors: [numC] },
                offsetY: -8,
            },
            tooltip: { y: { formatter: v => v + " pedidos" } },
        });
        this._charts.semanas = c; c.render();
    }

    // ── 9 · HBar máquinas activas hoy vs semana (TEXPLUS) ────────────────────
    _chartMaquinas(d, dk) {
        const el    = this.r9.el; if (!el) return;
        const items = (d.maquinas.top_maquinas || []).slice(0, 12);
        if (!items.length) return;
        const lblC  = dk ? "#cbd5e1" : "#374151";
        const colors = items.map(m => MAQ_COLORS[m.tipo] || C.slate);
        const c = new window.ApexCharts(el, {
            ...base(dk),
            chart: { ...base(dk).chart, type: "bar", height: 380 },
            plotOptions: { bar: { horizontal: true, barHeight: "55%",
                                  borderRadius: 5, borderRadiusApplication: "end",
                                  distributed: true } },
            series: [{ name: "Cargas hoy", data: items.map(m => m.hoy) }],
            xaxis: {
                categories: items.map(m => m.desc.substring(0, 22)),
                labels: { ...axs(dk), formatter: v => Math.round(Number(v)) },
                axisBorder: { show: false }, axisTicks: { show: false },
            },
            yaxis: { labels: { style: { fontSize: "11px", fontFamily: FONT, colors: lblC }, maxWidth: 190 } },
            colors,
            legend: { show: false },
            dataLabels: {
                enabled: true, textAnchor: "start",
                style: { fontSize: "11px", fontFamily: FONT, colors: [lblC], fontWeight: 500 },
                formatter: v => v + " cargas", offsetX: 6,
            },
            tooltip: {
                custom: ({ dataPointIndex: i }) => {
                    const m = items[i];
                    const bg = dk ? "#1e293b" : "#ffffff";
                    const fg = dk ? "#f1f5f9" : "#0f172a";
                    return `<div style="padding:10px 14px;font-size:12px;font-family:${FONT};background:${bg};color:${fg};border-radius:8px">
                        <strong>${m.desc}</strong><br>
                        <span style="color:${MAQ_COLORS[m.tipo] || C.slate}">${m.tipo}</span><br>
                        Hoy: <strong>${m.hoy}</strong> cargas &nbsp;·&nbsp; Semana: <strong>${m.semana}</strong>
                    </div>`;
                },
            },
        });
        this._charts.maquinas = c; c.render();
    }

    // ── 10 · Grouped bar tendencia de máquinas últimos 7 días (TEXPLUS) ──────
    _chartTendenciaMaq(d, dk) {
        const el    = this.r10.el; if (!el) return;
        const items = d.maquinas.tendencia_maq || [];
        if (!items.length) return;
        const labels = items.map(r => {
            const d = new Date(r.dia + "T00:00:00");
            return d.toLocaleDateString("es-PE", { weekday: "short", day: "numeric", month: "short" });
        });
        const c = new window.ApexCharts(el, {
            ...base(dk),
            chart: { ...base(dk).chart, type: "bar", height: 280, stacked: false },
            series: [
                { name: "Tintorería", data: items.map(r => r.tintoreria) },
                { name: "Acabados",   data: items.map(r => r.acabados) },
                { name: "Preparado",  data: items.map(r => r.preparado) },
                { name: "Estampado",  data: items.map(r => r.estampado) },
            ],
            colors: [C.blue, C.teal, C.amber, C.pink],
            plotOptions: { bar: { columnWidth: "70%", borderRadius: 4, borderRadiusApplication: "end" } },
            xaxis: {
                categories: labels,
                labels: { ...axs(dk, "11px"), rotate: -20 },
                axisBorder: { show: false }, axisTicks: { show: false },
            },
            yaxis: { labels: axs(dk) },
            legend: { position: "top", horizontalAlign: "right", ...lgd(dk) },
            dataLabels: { enabled: false },
            tooltip: { shared: true, intersect: false,
                       y: { formatter: v => v + " cargas" } },
        });
        this._charts.tendenciaMaq = c; c.render();
    }

    // ── KPIs getter ───────────────────────────────────────────────────────────
    get kpis() {
        const d = this.state.data; if (!d) return [];
        const { pedidos, partidas } = d;
        const kgDone = pedidos.kilos_done >= 1000
            ? (pedidos.kilos_done / 1000).toFixed(1) + "k kg"
            : Math.round(pedidos.kilos_done) + " kg";
        const prox14 = (pedidos.proximos_vencer || []).length;
        return [
            { lbl: "Pedidos Activos",  raw: pedidos.total_activos, isKg: false,
              sub: pedidos.settled > 0 ? `${pedidos.settled} liquidados` : "Ninguno liquidado",
              fmt: n => n.toLocaleString("es-PE"),
              icon: "fa-clipboard-list", c: "#6366f1", bg: "#eef2ff", bgdk: "#312e81" },
            { lbl: "A Tiempo",         raw: pedidos.on_time,        isKg: false,
              sub: `${pedidos.pct_on_time}% cumplimiento`,
              fmt: n => n.toLocaleString("es-PE"),
              icon: "fa-check-circle",   c: "#16a34a", bg: "#dcfce7", bgdk: "#14532d" },
            { lbl: "Demorados",        raw: pedidos.delayed,        isKg: false,
              sub: pedidos.avg_delay > 0 ? `Prom. ${pedidos.avg_delay}d de retraso` : "",
              fmt: n => n.toLocaleString("es-PE"),
              icon: "fa-clock-o",        c: "#ef4444", bg: "#fee2e2", bgdk: "#7f1d1d" },
            { lbl: "Kg en Producción", raw: pedidos.kilos_activos,  isKg: true,
              sub: `Terminados: ${kgDone}`,
              fmt: n => n >= 1000 ? (n / 1000).toFixed(1) + "k kg" : n + " kg",
              icon: "fa-balance-scale",  c: "#7c3aed", bg: "#f5f3ff", bgdk: "#3b0764" },
            { lbl: "Partidas Activas", raw: partidas.total_activas, isKg: false,
              sub: `${partidas.por_area.length} áreas · ${partidas.por_proceso.length} procesos`,
              fmt: n => n.toLocaleString("es-PE"),
              icon: "fa-th-list",        c: "#0891b2", bg: "#e0f9fe", bgdk: "#164e63" },
            { lbl: "Vencen en 7 días", raw: pedidos.proximos_7d,    isKg: false,
              sub: prox14 > 0 ? `${prox14} en próximos 14 días` : "Sin urgentes en 14d",
              fmt: n => n.toLocaleString("es-PE"),
              icon: "fa-calendar-times-o", c: "#d97706", bg: "#fef3c7", bgdk: "#78350f" },
        ];
    }

    // ── KPI de actividad de máquinas (mostrar solo si TEXPLUS disponible) ─────
    get kpiMaquinas() {
        const d = this.state.data;
        if (!d || !d.maquinas || !d.maquinas.disponible) return null;
        const maq = d.maquinas;
        const totalHoy = maq.top_maquinas.reduce((s, m) => s + m.hoy, 0);
        const totalSem = maq.top_maquinas.reduce((s, m) => s + m.semana, 0);
        const actHoy   = maq.top_maquinas.filter(m => m.hoy > 0).length;
        return { totalHoy, totalSem, actHoy };
    }
}

registry.category("actions").add("plan_alpha_dashboard", DashboardAlpha);
