/** @odoo-module **/

import { Component, useState, onWillStart, onMounted, onWillUnmount, useRef } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { rpc } from "@web/core/network/rpc";
import { useService } from "@web/core/utils/hooks";
import { loadBundle } from "@web/core/assets";

const AREA_COLORS = [
    "#f59e0b", "#10b981", "#3b82f6", "#8b5cf6",
    "#ec4899", "#06b6d4", "#84cc16", "#f97316",
];

const PROCESO_COLORS = [
    "#6366f1", "#f59e0b", "#10b981", "#3b82f6", "#8b5cf6",
    "#ec4899", "#06b6d4", "#84cc16", "#f97316", "#ef4444",
    "#14b8a6", "#a855f7",
];

const STATE_LABELS = {
    on: "A Tiempo",
    de: "Retrasados",
    do: "Terminados",
    se: "Liquidados",
};

const STATE_COLORS = {
    on: "#10b981",
    de: "#ef4444",
    do: "#3b82f6",
    se: "#94a3b8",
};

const CHART_DEFAULTS = {
    color: "#94a3b8",
    gridColor: "rgba(255,255,255,0.06)",
    font: { size: 11, family: "'Inter','Roboto',system-ui,sans-serif" },
};

// Icono y color distintivo para cada área de Programación
const AREA_ICON_CONFIG = {
    hilanderia: { icon: "fa-circle-o-notch", color: "#f59e0b", label: "Hilandería" },
    tejeduria:  { icon: "fa-th",             color: "#3b82f6", label: "Tejeduría"  },
    tintoreria: { icon: "fa-tint",           color: "#14b8a6", label: "Tintorería" },
    estampado:  { icon: "fa-paint-brush",    color: "#8b5cf6", label: "Estampado"  },
    acabado:    { icon: "fa-cut",            color: "#10b981", label: "Acabado"    },
    calidad:    { icon: "fa-star",           color: "#06b6d4", label: "Calidad"    },
};

const GRID_COLS = 20;
const GRID_EXTRA_ROWS = 3;

export class PlanGeneralDashboard extends Component {
    static template = "idtx_plan_general.Dashboard";
    static props = ["*"];

    setup() {
        this.actionService = useService("action");

        this.state = useState({
            loading: true,
            activeTab: "dashboard",
            activeProgramacion: "hilanderia",
            maquinas: [],
            maquinasLoading: false,
            ganttLoading: false,
            ganttOffsetDays: 0,
            ganttZoom: "week",
            ganttStates: { on: true, de: true, do: false },
            ganttArea: "todas",
            lastUpdate: null,
            pedidos: {
                total_activos: 0,
                on_time: 0,
                delayed: 0,
                done: 0,
                settled: 0,
                kilos_total: 0,
                kilos_done: 0,
                avg_delay: 0,
                total_clientes: 0,
                clientes_retrasados: 0,
                all_count: 0,
                top_delayed: [],
                proximos_vencer: [],
                top_clientes: [],
                estado_dist: [],
            },
            partidas: {
                total_activas: 0,
                sin_avance: 0,
                por_area: [],
                por_proceso: [],
            },
        });

        // Gantt refs + state
        this.refGanttBoard = useRef("ganttBoard");
        this._ganttRows    = [];
        this._ganttLoaded  = false;

        // Chart refs
        this.refDonut    = useRef("chartDonut");
        this.refBar      = useRef("chartBar");
        this.refHBar     = useRef("chartHBar");
        this.refClientes = useRef("chartClientes");
        this.refProceso  = useRef("chartProceso");
        this.refEstados  = useRef("chartEstados");

        this._charts = {};
        this._refreshTimer = null;

        onWillStart(async () => {
            await loadBundle("web.chartjs_lib");
        });

        onMounted(async () => {
            await this._loadData();
            this._refreshTimer = setInterval(() => this._loadData(), 5 * 60 * 1000);
        });

        onWillUnmount(() => {
            if (this._refreshTimer) clearInterval(this._refreshTimer);
            Object.values(this._charts).forEach((c) => c && c.destroy());
        });
    }

    // ── Navigation ───────────────────────────────────────────────────────────

    onBack() {
        this.actionService.doAction({ type: "ir.actions.client", tag: "home" });
    }

    onNavClick(ev) {
        const tab = ev.currentTarget.dataset.tab;
        if (tab === this.state.activeTab) return;
        this.state.activeTab = tab;
        if (tab === "dashboard") {
            setTimeout(() => this._renderCharts(), 60);
        } else if (tab === "programacion") {
            this._loadMaquinas(this.state.activeProgramacion);
        } else if (tab === "planning") {
            setTimeout(() => {
                if (!this._ganttLoaded) this._loadGanttData();
                else this._renderGanttBoard();
            }, 60);
        }
    }

    get navTabs() {
        return [
            { key: "dashboard",     label: "Dashboard",     icon: "fa-tachometer"   },
            { key: "tablas",        label: "Tablas",        icon: "fa-table"        },
            { key: "programacion",  label: "Programación",  icon: "fa-tasks"        },
            { key: "planning",      label: "Planning",      icon: "fa-calendar"     },
            { key: "configuracion", label: "Configuración", icon: "fa-cog"          },
        ];
    }

    get programacionAreas() {
        return [
            { key: "hilanderia",  label: "Hilandería",  icon: "fa-circle-o-notch" },
            { key: "tejeduria",   label: "Tejeduría",   icon: "fa-th"             },
            { key: "tintoreria",  label: "Tintorería",  icon: "fa-tint"           },
            { key: "estampado",   label: "Estampado",   icon: "fa-paint-brush"    },
            { key: "acabado",     label: "Acabado",     icon: "fa-check-square-o" },
            { key: "calidad",     label: "Calidad",     icon: "fa-shield"         },
        ];
    }

    onProgramacionAreaClick(ev) {
        const area = ev.currentTarget.dataset.area;
        if (area && area !== this.state.activeProgramacion) {
            this.state.activeProgramacion = area;
            this._loadMaquinas(area);
        }
    }

    async _loadMaquinas(area) {
        this.state.maquinasLoading = true;
        try {
            const data = await rpc("/idtx_plan_general/programacion_data", { area });
            this.state.maquinas = data.machines || [];
        } catch (e) {
            console.error("[PlanGeneral] Error cargando máquinas:", e);
            this.state.maquinas = [];
        } finally {
            this.state.maquinasLoading = false;
        }
    }

    // ── Grid de máquinas ─────────────────────────────────────────────────────

    get gridSlots() {
        const machines = this.state.maquinas;
        const maxSlot = machines.length
            ? Math.max(...machines.map(m => m.slot_index))
            : -1;
        const minSlots =
            (Math.ceil((machines.length + 1) / GRID_COLS) + GRID_EXTRA_ROWS) * GRID_COLS;
        const total = Math.max(
            minSlots,
            (Math.ceil((maxSlot + 1) / GRID_COLS) + GRID_EXTRA_ROWS) * GRID_COLS
        );
        const occupied = new Map(machines.map(m => [m.slot_index, m]));
        return Array.from({ length: total }, (_, i) => ({
            index: i,
            machine: occupied.get(i) || null,
        }));
    }

    get currentAreaConfig() {
        return AREA_ICON_CONFIG[this.state.activeProgramacion] ||
            { icon: "fa-cogs", color: "#94a3b8", label: "" };
    }

    // ── Drag & Drop ───────────────────────────────────────────────────────────

    onMachineDragStart(ev) {
        const el = ev.currentTarget;
        this._dragId   = parseInt(el.dataset.machineId);
        this._dragSlot = parseInt(el.dataset.slot);
        ev.dataTransfer.effectAllowed = "move";
        ev.dataTransfer.setData("text/plain", String(this._dragId));
        // visually dim after next tick
        setTimeout(() => el.classList.add("pg-machine--dragging"), 0);
    }

    onMachineDragEnd(ev) {
        ev.currentTarget.classList.remove("pg-machine--dragging");
        this._dragId   = null;
        this._dragSlot = null;
        // remove all drag-over highlights
        document.querySelectorAll(".pg-slot--over").forEach(el =>
            el.classList.remove("pg-slot--over")
        );
    }

    onSlotDragOver(ev) {
        ev.preventDefault();
        ev.dataTransfer.dropEffect = "move";
        ev.currentTarget.classList.add("pg-slot--over");
    }

    onSlotDragLeave(ev) {
        ev.currentTarget.classList.remove("pg-slot--over");
    }

    async onSlotDrop(ev) {
        ev.preventDefault();
        ev.currentTarget.classList.remove("pg-slot--over");

        const targetSlot = parseInt(ev.currentTarget.dataset.slot);
        const dragId   = this._dragId;
        const fromSlot = this._dragSlot;

        if (dragId === null || dragId === undefined || targetSlot === fromSlot) return;

        const machines = this.state.maquinas.map(m => ({ ...m }));
        const draggedIdx = machines.findIndex(m => m.id === dragId);
        if (draggedIdx === -1) return;

        // Si el slot destino está ocupado, intercambiar posiciones
        const targetIdx = machines.findIndex(m => m.slot_index === targetSlot);
        if (targetIdx !== -1) {
            machines[targetIdx].slot_index = fromSlot;
            this._savePosition(machines[targetIdx].id, fromSlot);
        }

        machines[draggedIdx].slot_index = targetSlot;
        this.state.maquinas = machines;

        this._savePosition(dragId, targetSlot);
    }

    async _savePosition(machineId, slotIndex) {
        try {
            await rpc("/idtx_plan_general/save_machine_position", {
                equipment_id: machineId,
                area: this.state.activeProgramacion,
                slot_index: slotIndex,
            });
        } catch (e) {
            console.error("[PlanGeneral] Error guardando posición:", e);
        }
    }

    // ── Gantt (Planning) ─────────────────────────────────────────────────────

    async _loadGanttData() {
        this.state.ganttLoading = true;
        try {
            const data = await rpc("/idtx_plan_general/planning_data", {});
            this._ganttRows  = data.rows || [];
            this._ganttLoaded = true;
        } catch (e) {
            console.error("[PlanGeneral] Error cargando planning:", e);
        } finally {
            this.state.ganttLoading = false;
            setTimeout(() => this._renderGanttBoard(), 60);
        }
    }

    _ganttRange() {
        const today = new Date();
        today.setHours(0, 0, 0, 0);
        const ZOOM = {
            day:   { days: 30,  anchor: 9  },
            week:  { days: 91,  anchor: 28 },
            month: { days: 182, anchor: 56 },
        };
        const { days: rd, anchor } = ZOOM[this.state.ganttZoom] || ZOOM.week;
        const s = new Date(today);
        s.setDate(s.getDate() - anchor + this.state.ganttOffsetDays);
        return { today, start: s, days: rd };
    }

    _ganttNavStep() {
        return { day: 7, week: 28, month: 56 }[this.state.ganttZoom] || 28;
    }

    get ganttNavLabel() {
        return { day: "1 sem", week: "4 sem", month: "2 mes" }[this.state.ganttZoom] || "4 sem";
    }

    _pct(date, rangeStart, rangeDays) {
        return ((date - rangeStart) / (rangeDays * 86400000)) * 100;
    }

    _renderGanttBoard() {
        const el = this.refGanttBoard ? this.refGanttBoard.el : null;
        if (!el) return;

        const { today, start: rs, days: rd } = this._ganttRange();

        const AREA_KEYS = {
            hilanderia: ["HILAND"],
            tejeduria:  ["TEJED"],
            tintoreria: ["TINTOR", "TINTE"],
            estampado:  ["ESTAMP"],
            acabado:    ["ACAB"],
            calidad:    ["CALID", " QC", " QA"],
        };

        const stF = this.state.ganttStates;
        const aF  = this.state.ganttArea;

        const filtered = this._ganttRows.filter(r => {
            if (!stF[r.state]) return false;
            if (aF !== "todas") {
                const norm = (r.area || "").toUpperCase()
                    .normalize("NFD").replace(/[\u0300-\u036f]/g, "");
                return (AREA_KEYS[aF] || []).some(k => norm.includes(k.trim()));
            }
            return true;
        });

        // Group by area
        const groups = new Map();
        filtered.forEach(r => {
            const k = (r.area || "SIN ÁREA").toUpperCase();
            if (!groups.has(k)) groups.set(k, []);
            groups.get(k).push(r);
        });

        const todayPct = Math.max(-5, Math.min(105, this._pct(today, rs, rd)));

        // ── Header HTML ───────────────────────────────────────────────────────
        const headerHtml = this._ganttBuildHeader(rs, rd);

        // ── Rows HTML ─────────────────────────────────────────────────────────
        const STATE_CLASS = { on: "pg-gantt-bar--on", de: "pg-gantt-bar--de", do: "pg-gantt-bar--do", se: "pg-gantt-bar--se" };
        let rowsHtml = "";

        if (!groups.size) {
            rowsHtml = `<div class="pg-gantt-empty">
                <i class="fa fa-calendar-times-o"></i>
                <span>Sin pedidos para los filtros seleccionados</span>
            </div>`;
        } else {
            [...groups.entries()].sort(([a], [b]) => a.localeCompare(b)).forEach(([area, rows]) => {
                rowsHtml += `<div class="pg-gantt-group">
                    <div class="pg-gantt-group-hdr">
                        <i class="fa fa-chevron-down"></i>
                        <span>${area}</span>
                        <span class="pg-gantt-group-count">${rows.length}</span>
                    </div>`;

                rows.forEach(r => {
                    const sD = new Date(r.start + "T00:00:00");
                    const eD = new Date(r.end   + "T00:00:00");
                    const lP = this._pct(sD, rs, rd);
                    const wP = Math.max(0.6, this._pct(eD, rs, rd) - lP);
                    const delayed = r.state === "de"
                        ? `<span class="pg-gantt-bar-delay">+${r.num_days}d</span>` : "";
                    const tip = encodeURIComponent(JSON.stringify({
                        num: r.num, customer: r.customer, area: r.area,
                        state: r.state, start: r.start, end: r.end,
                        weight: r.weight, num_days: r.num_days,
                    }));
                    rowsHtml += `<div class="pg-gantt-row">
                        <div class="pg-gantt-row-label">
                            <span class="pg-gantt-row-num">${r.num}</span>
                            <span class="pg-gantt-row-cust">${r.customer}</span>
                        </div>
                        <div class="pg-gantt-row-track">
                            <div class="${"pg-gantt-bar " + (STATE_CLASS[r.state] || "")}"
                                 style="left:${lP}%;width:${wP}%"
                                 data-tip="${tip}">
                                <span class="pg-gantt-bar-label">${r.num}${delayed}</span>
                            </div>
                        </div>
                    </div>`;
                });

                rowsHtml += `</div>`;
            });
        }

        // ── Assemble ──────────────────────────────────────────────────────────
        el.innerHTML = `
            <div class="pg-gantt-board pg-gantt-board--${this.state.ganttZoom}" style="--today:${todayPct}%">
                <div class="pg-gantt-hdr-row">
                    <div class="pg-gantt-label-col"></div>
                    <div class="pg-gantt-time-col">
                        ${headerHtml}
                    </div>
                </div>
                <div class="pg-gantt-rows">
                    ${rowsHtml}
                </div>
            </div>`;

        // Bind tooltip events
        el.querySelectorAll("[data-tip]").forEach(bar => {
            bar.addEventListener("mouseenter", ev => this._ganttShowTip(ev));
            bar.addEventListener("mouseleave", () => this._ganttHideTip());
        });
    }

    _ganttShowTip(ev) {
        try {
            const data = JSON.parse(decodeURIComponent(ev.currentTarget.dataset.tip));
            const SL = { on: "A Tiempo", de: "Retrasado", do: "Terminado", se: "Liquidado" };
            const tip = document.getElementById("pg-gantt-tooltip");
            if (!tip) return;
            const delayLine = data.state === "de"
                ? `<div class="pg-tip-delay"><i class="fa fa-clock-o"></i> +${data.num_days} días de retraso</div>` : "";
            tip.innerHTML = `
                <div class="pg-tip-head">${data.num}</div>
                <div class="pg-tip-cust">${data.customer}</div>
                <div class="pg-tip-row"><i class="fa fa-map-marker"></i>${data.area}</div>
                <div class="pg-tip-row"><i class="fa fa-calendar-o"></i>${data.start} → ${data.end}</div>
                <div class="pg-tip-row"><i class="fa fa-balance-scale"></i>${data.weight} kg</div>
                <div class="pg-tip-state pg-tip-state--${data.state}">${SL[data.state] || data.state}</div>
                ${delayLine}`;
            tip.style.display = "block";
            this._ganttMoveTip(ev);
            this._boundTipMove = e => this._ganttMoveTip(e);
            ev.currentTarget.addEventListener("mousemove", this._boundTipMove);
        } catch (e) { /* ignore */ }
    }

    _ganttMoveTip(ev) {
        const tip = document.getElementById("pg-gantt-tooltip");
        if (!tip) return;
        const x = Math.min(ev.clientX + 16, window.innerWidth - tip.offsetWidth - 12);
        tip.style.left = x + "px";
        tip.style.top  = (ev.clientY - 14) + "px";
    }

    _ganttHideTip() {
        const tip = document.getElementById("pg-gantt-tooltip");
        if (tip) tip.style.display = "none";
        if (this._boundTipMove) {
            document.removeEventListener("mousemove", this._boundTipMove);
            this._boundTipMove = null;
        }
    }

    onGanttPrev() {
        this.state.ganttOffsetDays -= this._ganttNavStep();
        setTimeout(() => this._renderGanttBoard(), 0);
    }

    onGanttNext() {
        this.state.ganttOffsetDays += this._ganttNavStep();
        setTimeout(() => this._renderGanttBoard(), 0);
    }

    onGanttToday() {
        this.state.ganttOffsetDays = 0;
        setTimeout(() => this._renderGanttBoard(), 0);
    }

    onGanttZoom(ev) {
        const z = ev.currentTarget.dataset.zoom;
        if (z && z !== this.state.ganttZoom) {
            this.state.ganttZoom = z;
            this.state.ganttOffsetDays = 0;
            setTimeout(() => this._renderGanttBoard(), 0);
        }
    }

    _ganttBuildHeader(rs, rd) {
        const zoom = this.state.ganttZoom;
        const endDate = new Date(rs.getTime() + rd * 86400000);
        const MON = ["Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"];
        const MS = (d) => Math.max(d.getTime(), rs.getTime());
        const ME = (d) => Math.min(d.getTime(), endDate.getTime());
        const pct = (t) => ((t - rs) / (rd * 86400000)) * 100;

        // Shared: month band positions
        const monthBands = () => {
            const bands = [];
            const c = new Date(rs.getFullYear(), rs.getMonth(), 1);
            while (c <= endDate) {
                const s = MS(c), e = ME(new Date(c.getFullYear(), c.getMonth() + 1, 1));
                bands.push({ label: `${MON[c.getMonth()]} ${c.getFullYear()}`, l: pct(s), w: pct(e) - pct(s) });
                c.setMonth(c.getMonth() + 1);
            }
            return bands;
        };

        // ── DAY zoom ─────────────────────────────────────────────────────────
        if (zoom === "day") {
            // Row 1: months
            let r1 = `<div class="pg-gantt-months">`;
            monthBands().forEach(m => {
                r1 += `<div class="pg-gantt-month" style="left:${m.l}%;width:${m.w}%"><span>${m.label}</span></div>`;
            });
            r1 += `</div>`;

            // Row 2: individual days
            const DOW = ["D","L","M","X","J","V","S"];
            let r2 = `<div class="pg-gantt-days">`;
            for (let i = 0; i < rd; i++) {
                const d = new Date(rs.getTime() + i * 86400000);
                const dow = d.getDay();
                const isWE = dow === 0 || dow === 6;
                const l = (i / rd) * 100;
                const w = (1  / rd) * 100;
                r2 += `<div class="pg-gantt-day${isWE ? " pg-gantt-day--we" : ""}" style="left:${l}%;width:${w}%">
                    <span class="pg-gantt-day-dn">${DOW[dow]}</span>
                    <span class="pg-gantt-day-dd">${d.getDate()}</span>
                </div>`;
            }
            r2 += `</div>`;
            return r1 + r2;
        }

        // ── MONTH zoom ────────────────────────────────────────────────────────
        if (zoom === "month") {
            // Row 1: years
            const yearMap = new Map();
            const c = new Date(rs.getFullYear(), rs.getMonth(), 1);
            while (c <= endDate) {
                const yr = c.getFullYear();
                if (!yearMap.has(yr)) {
                    const yS = MS(new Date(yr, 0, 1));
                    const yE = ME(new Date(yr + 1, 0, 1));
                    yearMap.set(yr, { l: pct(yS), w: pct(yE) - pct(yS) });
                }
                c.setMonth(c.getMonth() + 1);
            }
            let r1 = `<div class="pg-gantt-years">`;
            yearMap.forEach((b, yr) => {
                r1 += `<div class="pg-gantt-year" style="left:${b.l}%;width:${b.w}%"><span>${yr}</span></div>`;
            });
            r1 += `</div>`;

            // Row 2: months (only short name)
            let r2 = `<div class="pg-gantt-months">`;
            monthBands().forEach(m => {
                r2 += `<div class="pg-gantt-month" style="left:${m.l}%;width:${m.w}%"><span>${m.label.split(" ")[0]}</span></div>`;
            });
            r2 += `</div>`;
            return r1 + r2;
        }

        // ── WEEK zoom (default) ───────────────────────────────────────────────
        let r1 = `<div class="pg-gantt-months">`;
        monthBands().forEach(m => {
            r1 += `<div class="pg-gantt-month" style="left:${m.l}%;width:${m.w}%"><span>${m.label}</span></div>`;
        });
        r1 += `</div>`;

        let r2 = `<div class="pg-gantt-weeks">`;
        const wCur = new Date(rs);
        wCur.setDate(wCur.getDate() - ((wCur.getDay() + 6) % 7));
        while (wCur <= endDate) {
            const wS = MS(wCur);
            const wEC = ME(new Date(wCur.getTime() + 7 * 86400000));
            if (wEC > rs.getTime()) {
                const l = Math.max(0, pct(wS));
                const w = pct(wEC) - Math.max(0, pct(wS));
                const jan1 = new Date(wCur.getFullYear(), 0, 1);
                const wNum = Math.ceil(((wCur - jan1) / 86400000 + jan1.getDay() + 1) / 7);
                r2 += `<div class="pg-gantt-week" style="left:${l}%;width:${w}%">S${wNum}</div>`;
            }
            wCur.setDate(wCur.getDate() + 7);
        }
        r2 += `</div>`;
        return r1 + r2;
    }

    onGanttToggleState(ev) {
        const s = ev.currentTarget.dataset.state;
        this.state.ganttStates = { ...this.state.ganttStates, [s]: !this.state.ganttStates[s] };
        setTimeout(() => this._renderGanttBoard(), 0);
    }

    onGanttAreaFilter(ev) {
        this.state.ganttArea = ev.currentTarget.dataset.area;
        setTimeout(() => this._renderGanttBoard(), 0);
    }

    // ── Data loading ─────────────────────────────────────────────────────────

    async _loadData() {
        this.state.loading = true;
        try {
            const data = await rpc("/idtx_plan_general/dashboard_data", {});
            this.state.pedidos  = data.pedidos;
            this.state.partidas = data.partidas;
            this.state.lastUpdate = new Date();
        } catch (e) {
            console.error("[PlanGeneral] Error cargando datos:", e);
        } finally {
            this.state.loading = false;
            setTimeout(() => this._renderCharts(), 60);
        }
    }

    async onRefresh() {
        await this._loadData();
    }

    // ── Chart rendering ───────────────────────────────────────────────────────

    _renderCharts() {
        this._renderDonut();
        this._renderBar();
        this._renderHBar();
        this._renderClientes();
        this._renderProceso();
        this._renderEstados();
    }

    _destroyChart(key) {
        if (this._charts[key]) {
            this._charts[key].destroy();
            this._charts[key] = null;
        }
    }

    // Donut: distribución estados activos
    _renderDonut() {
        const canvas = this.refDonut.el;
        if (!canvas) return;
        this._destroyChart("donut");

        const p = this.state.pedidos;
        const raw = [
            { label: STATE_LABELS.on, value: p.on_time,  color: STATE_COLORS.on },
            { label: STATE_LABELS.de, value: p.delayed,  color: STATE_COLORS.de },
            { label: STATE_LABELS.do, value: p.done,     color: STATE_COLORS.do },
            { label: STATE_LABELS.se, value: p.settled,  color: STATE_COLORS.se },
        ].filter((d) => d.value > 0);

        if (!raw.length) return;

        this._charts.donut = new window.Chart(canvas, {
            type: "doughnut",
            data: {
                labels: raw.map((d) => d.label),
                datasets: [{
                    data: raw.map((d) => d.value),
                    backgroundColor: raw.map((d) => d.color),
                    borderColor: "#0d1117",
                    borderWidth: 3,
                    hoverOffset: 8,
                }],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                cutout: "68%",
                plugins: {
                    legend: {
                        position: "bottom",
                        labels: { color: CHART_DEFAULTS.color, font: CHART_DEFAULTS.font, padding: 12, boxWidth: 12 },
                    },
                    tooltip: { callbacks: { label: (ctx) => ` ${ctx.label}: ${ctx.parsed}` } },
                },
            },
        });
    }

    // Bar vertical: kilos por área
    _renderBar() {
        const canvas = this.refBar.el;
        if (!canvas) return;
        this._destroyChart("bar");

        const areas = this.state.partidas.por_area;
        if (!areas.length) return;

        this._charts.bar = new window.Chart(canvas, {
            type: "bar",
            data: {
                labels: areas.map((a) => a.area),
                datasets: [{
                    label: "Kilos",
                    data: areas.map((a) => a.kilos),
                    backgroundColor: AREA_COLORS.slice(0, areas.length).map((c) => c + "cc"),
                    borderColor: AREA_COLORS.slice(0, areas.length),
                    borderWidth: 1.5,
                    borderRadius: 4,
                }],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    tooltip: { callbacks: { label: (ctx) => ` ${this.fmtKilos(ctx.parsed.y)}` } },
                },
                scales: {
                    x: {
                        ticks: { color: CHART_DEFAULTS.color, font: CHART_DEFAULTS.font, maxRotation: 35, minRotation: 25 },
                        grid: { color: CHART_DEFAULTS.gridColor },
                    },
                    y: {
                        ticks: { color: CHART_DEFAULTS.color, font: CHART_DEFAULTS.font, callback: (v) => this.fmtKilos(v) },
                        grid: { color: CHART_DEFAULTS.gridColor },
                    },
                },
            },
        });
    }

    // H-Bar: top retrasados por días
    _renderHBar() {
        const canvas = this.refHBar.el;
        if (!canvas) return;
        this._destroyChart("hbar");

        const delayed = this.state.pedidos.top_delayed;
        if (!delayed.length) return;

        this._charts.hbar = new window.Chart(canvas, {
            type: "bar",
            data: {
                labels: delayed.map((d) => d.num),
                datasets: [{
                    label: "Días",
                    data: delayed.map((d) => d.days),
                    backgroundColor: delayed.map((d) => d.days > 25 ? "#ef444499" : "#f97316aa"),
                    borderColor:     delayed.map((d) => d.days > 25 ? "#ef4444"   : "#f97316"),
                    borderWidth: 1.5,
                    borderRadius: 4,
                }],
            },
            options: {
                indexAxis: "y",
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        callbacks: {
                            label: (ctx) => ` ${ctx.parsed.x} días`,
                            afterLabel: (ctx) => {
                                const d = delayed[ctx.dataIndex];
                                return d ? ` ${d.customer}` : "";
                            },
                        },
                    },
                },
                scales: {
                    x: { ticks: { color: CHART_DEFAULTS.color, font: CHART_DEFAULTS.font }, grid: { color: CHART_DEFAULTS.gridColor } },
                    y: { ticks: { color: "#e6eefb",            font: CHART_DEFAULTS.font }, grid: { color: "rgba(255,255,255,0.04)" } },
                },
            },
        });
    }

    // H-Bar: top clientes por kilos
    _renderClientes() {
        const canvas = this.refClientes.el;
        if (!canvas) return;
        this._destroyChart("clientes");

        const clientes = this.state.pedidos.top_clientes;
        if (!clientes.length) return;

        const labels = clientes.map((c) =>
            c.customer.length > 22 ? c.customer.slice(0, 20) + "…" : c.customer
        );

        this._charts.clientes = new window.Chart(canvas, {
            type: "bar",
            data: {
                labels,
                datasets: [
                    {
                        label: "Kilos",
                        data: clientes.map((c) => c.kilos),
                        backgroundColor: "#3b82f6bb",
                        borderColor: "#3b82f6",
                        borderWidth: 1.5,
                        borderRadius: 4,
                    },
                    {
                        label: "Retrasados",
                        data: clientes.map((c) => c.delayed),
                        backgroundColor: "#ef444466",
                        borderColor: "#ef4444",
                        borderWidth: 1.5,
                        borderRadius: 4,
                        yAxisID: "yRight",
                    },
                ],
            },
            options: {
                indexAxis: "y",
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: "top",
                        labels: { color: CHART_DEFAULTS.color, font: { size: 10 }, boxWidth: 10, padding: 10 },
                    },
                    tooltip: {
                        callbacks: {
                            label: (ctx) =>
                                ctx.datasetIndex === 0
                                    ? ` Kilos: ${this.fmtKilos(ctx.parsed.x)}`
                                    : ` Retrasados: ${ctx.parsed.x}`,
                        },
                    },
                },
                scales: {
                    x: {
                        ticks: { color: CHART_DEFAULTS.color, font: CHART_DEFAULTS.font, callback: (v) => this.fmtKilos(v) },
                        grid: { color: CHART_DEFAULTS.gridColor },
                    },
                    y: {
                        ticks: { color: "#e6eefb", font: { size: 10 } },
                        grid: { color: "rgba(255,255,255,0.04)" },
                    },
                    yRight: {
                        position: "right",
                        display: false,
                        grid: { drawOnChartArea: false },
                    },
                },
            },
        });
    }

    // Bar vertical: partidas por proceso
    _renderProceso() {
        const canvas = this.refProceso.el;
        if (!canvas) return;
        this._destroyChart("proceso");

        const procs = this.state.partidas.por_proceso;
        if (!procs.length) return;

        this._charts.proceso = new window.Chart(canvas, {
            type: "bar",
            data: {
                labels: procs.map((p) =>
                    p.proceso.length > 14 ? p.proceso.slice(0, 12) + "…" : p.proceso
                ),
                datasets: [{
                    label: "Partidas",
                    data: procs.map((p) => p.count),
                    backgroundColor: PROCESO_COLORS.slice(0, procs.length).map((c) => c + "bb"),
                    borderColor:     PROCESO_COLORS.slice(0, procs.length),
                    borderWidth: 1.5,
                    borderRadius: 4,
                }],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        callbacks: {
                            label: (ctx) => ` ${ctx.parsed.y} partidas`,
                            afterLabel: (ctx) => {
                                const p = procs[ctx.dataIndex];
                                return p ? ` ${this.fmtKilos(p.kilos)}` : "";
                            },
                        },
                    },
                },
                scales: {
                    x: {
                        ticks: { color: CHART_DEFAULTS.color, font: { size: 9 }, maxRotation: 40, minRotation: 30 },
                        grid: { color: CHART_DEFAULTS.gridColor },
                    },
                    y: {
                        ticks: { color: CHART_DEFAULTS.color, font: CHART_DEFAULTS.font },
                        grid: { color: CHART_DEFAULTS.gridColor },
                    },
                },
            },
        });
    }

    // Polar/Radar: estados históricos (todos los pedidos)
    _renderEstados() {
        const canvas = this.refEstados.el;
        if (!canvas) return;
        this._destroyChart("estados");

        const dist = this.state.pedidos.estado_dist;
        if (!dist || !dist.length) return;

        this._charts.estados = new window.Chart(canvas, {
            type: "polarArea",
            data: {
                labels: dist.map((d) => d.estado),
                datasets: [{
                    data: dist.map((d) => d.count),
                    backgroundColor: dist.map((d) => d.color + "99"),
                    borderColor:     dist.map((d) => d.color),
                    borderWidth: 1.5,
                }],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: "bottom",
                        labels: { color: CHART_DEFAULTS.color, font: CHART_DEFAULTS.font, padding: 10, boxWidth: 12 },
                    },
                    tooltip: { callbacks: { label: (ctx) => ` ${ctx.label}: ${ctx.parsed.r}` } },
                },
                scales: {
                    r: {
                        ticks: { color: CHART_DEFAULTS.color, font: { size: 9 }, backdropColor: "transparent" },
                        grid:  { color: "rgba(255,255,255,0.06)" },
                        pointLabels: { color: CHART_DEFAULTS.color },
                    },
                },
            },
        });
    }

    // ── Getters ───────────────────────────────────────────────────────────────

    get pctOnTime() {
        const total = this.state.pedidos.total_activos;
        if (!total) return 0;
        return Math.round((this.state.pedidos.on_time / total) * 100);
    }

    get pctDelayed() {
        const total = this.state.pedidos.total_activos;
        if (!total) return 0;
        return Math.round((this.state.pedidos.delayed / total) * 100);
    }

    get areasWithPct() {
        const areas = this.state.partidas.por_area;
        if (!areas.length) return [];
        const maxKilos = Math.max(...areas.map((a) => a.kilos), 1);
        return areas.map((a, i) => ({
            ...a,
            pct:   Math.round((a.kilos / maxKilos) * 100),
            color: AREA_COLORS[i % AREA_COLORS.length],
        }));
    }

    get clientesWithPct() {
        const clientes = this.state.pedidos.top_clientes;
        if (!clientes.length) return [];
        const maxKilos = Math.max(...clientes.map((c) => c.kilos), 1);
        return clientes.map((c, i) => ({
            ...c,
            pct:   Math.round((c.kilos / maxKilos) * 100),
            color: AREA_COLORS[i % AREA_COLORS.length],
        }));
    }

    // ── Helpers ───────────────────────────────────────────────────────────────

    fmtKilos(k) {
        if (k === null || k === undefined) return "—";
        if (k >= 1000) return (k / 1000).toFixed(1) + " t";
        return Number(k).toFixed(0) + " kg";
    }

    fmtDate(s) {
        if (!s) return "—";
        const d = new Date(s);
        if (isNaN(d)) return s;
        return d.toLocaleDateString("es-PE", { day: "2-digit", month: "short", year: "numeric" });
    }

    fmtTime(d) {
        if (!d) return "—";
        return d.toLocaleTimeString("es-PE", { hour: "2-digit", minute: "2-digit" });
    }

    stateLabelOf(state) {
        return STATE_LABELS[state] || state;
    }
}

registry.category("actions").add("idtx_plan_general.dashboard", PlanGeneralDashboard);
