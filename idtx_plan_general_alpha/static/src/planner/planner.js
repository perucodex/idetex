/** @odoo-module **/

import { Component, useState, onWillStart, onMounted, onWillUnmount, useRef } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

// ── Constants ──────────────────────────────────────────────────────────────
const MONTHS      = ['Ene','Feb','Mar','Abr','May','Jun','Jul','Ago','Sep','Oct','Nov','Dic'];
const MONTHS_FULL = ['Enero','Febrero','Marzo','Abril','Mayo','Junio','Julio','Agosto','Septiembre','Octubre','Noviembre','Diciembre'];
const DOW         = ['Dom','Lun','Mar','Mié','Jue','Vie','Sáb'];
const DOW_SHORT   = ['D','L','M','X','J','V','S'];

const LS_KEY_SEL   = 'idtx_planner_sel_v1';
const LS_KEY_ZOOM  = 'idtx_planner_zoom';
const LS_KEY_STYLE = 'idtx_planner_bar_style';

const DAY_MS = 86400000;

// Ordered list of process areas for grouping
const AREA_ORDER = [
    'TEJEDURIA', 'PRE TINTORERIA', 'TINTORERIA', 'PRE ESTAMPADO',
    'ESTAMPADO', 'PRE ACABADO', 'ACABADO', 'CONTROL DE CALIDAD', 'CONFECCION',
];

// ── Date helpers ───────────────────────────────────────────────────────────
function parseDate(str) {
    if (!str) return null;
    // Handles both Date strings "YYYY-MM-DD" and Datetime "YYYY-MM-DD HH:MM:SS"
    return new Date(str.length === 10 ? str + 'T00:00:00' : str.replace(' ', 'T')).getTime();
}

function dateToOdooStr(ms) {
    const d = new Date(ms);
    const p = n => String(n).padStart(2, '0');
    return `${d.getFullYear()}-${p(d.getMonth()+1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}:00`;
}

function sod(ms)  { const d = new Date(ms); return new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime(); }
function sow(ms)  { const d = new Date(sod(ms)); return d.getTime() - ((d.getDay() + 6) % 7) * DAY_MS; }
function som(ms)  { const d = new Date(ms); return new Date(d.getFullYear(), d.getMonth(), 1).getTime(); }
function soy(ms)  { const d = new Date(ms); return new Date(d.getFullYear(), 0, 1).getTime(); }

function addMonths(ms, n) { const d = new Date(ms); return new Date(d.getFullYear(), d.getMonth() + n, 1).getTime(); }
function addYears(ms, n)  { const d = new Date(ms); return new Date(d.getFullYear() + n, 0, 1).getTime(); }
function isWeekend(ms)    { const g = new Date(ms).getDay(); return g === 0 || g === 6; }

function formatShort(ms) {
    const d = new Date(ms);
    return d.getDate() + ' ' + MONTHS[d.getMonth()] + ' ' + String(d.getFullYear()).slice(2);
}

function pad2(n) { return String(n).padStart(2, '0'); }

// ── Area & status metadata ─────────────────────────────────────────────────
function areaMeta(area) {
    const key = (area || '').toUpperCase().trim();
    if (key === 'TEJEDURIA')          return { color: 'var(--plr-area-tej)',     soft: 'var(--plr-area-tej-soft)' };
    if (key === 'PRE TINTORERIA')     return { color: 'var(--plr-area-pretin)',  soft: 'var(--plr-area-pretin-soft)' };
    if (key === 'TINTORERIA')         return { color: 'var(--plr-area-tin)',     soft: 'var(--plr-area-tin-soft)' };
    if (key === 'PRE ESTAMPADO')      return { color: 'var(--plr-area-preest)',  soft: 'var(--plr-area-preest-soft)' };
    if (key === 'ESTAMPADO')          return { color: 'var(--plr-area-est)',     soft: 'var(--plr-area-est-soft)' };
    if (key === 'PRE ACABADO')        return { color: 'var(--plr-area-preacab)', soft: 'var(--plr-area-preacab-soft)' };
    if (key === 'ACABADO')            return { color: 'var(--plr-area-acab)',    soft: 'var(--plr-area-acab-soft)' };
    if (key === 'CONTROL DE CALIDAD') return { color: 'var(--plr-area-acab)',    soft: 'var(--plr-area-acab-soft)' };
    if (key === 'CONFECCION')         return { color: 'var(--plr-area-confec)', soft: 'var(--plr-area-confec-soft)' };
    return { color: 'var(--plr-area-default)', soft: 'var(--plr-area-default-soft)' };
}

function statusMeta(end, progress, today) {
    if (progress >= 100)  return { label: 'Completado', color: 'var(--plr-status-done)', soft: 'var(--plr-status-done-soft)' };
    if (end < today)      return { label: 'Retrasado',  color: 'var(--plr-accent)',       soft: 'var(--plr-accent-soft)' };
    return                       { label: 'En proceso', color: 'var(--plr-status-prog)',  soft: 'var(--plr-status-prog-soft)' };
}

// ── localStorage helpers ───────────────────────────────────────────────────
function lsGet(key, fallback) {
    try { const v = localStorage.getItem(key); return v !== null ? JSON.parse(v) : fallback; }
    catch { return fallback; }
}
function lsSet(key, val) {
    try { if (val === null) localStorage.removeItem(key); else localStorage.setItem(key, JSON.stringify(val)); }
    catch {}
}

// ── Component ──────────────────────────────────────────────────────────────
export class PlannerView extends Component {
    static template = 'idtx_plan_general_alpha.Planner';

    setup() {
        this.orm           = useService('orm');
        this.actionService = useService('action');
        this.scrollRef     = useRef('scrollRef');

        this.st = useState({
            loading:  true,
            error:    null,
            zoom:     lsGet(LS_KEY_ZOOM, 'dias'),
            barStyle: lsGet(LS_KEY_STYLE, 'estado'),
            tasks:    [],
            // Start empty — user picks records via "Filtrar Pedidos"
            selIds:   (() => { const v = lsGet(LS_KEY_SEL, []); return Array.isArray(v) ? v : []; })(),
            picker: {
                open: false, loading: false,
                search: '', records: [], checked: [],
            },
        });

        this.today = Date.now();

        // Non-reactive drag state (avoids re-renders during mouse move)
        this.drag    = null;
        this._raf    = null;

        // Render cache — invalidated when tasks or zoom changes
        this._renderCache    = null;
        this._renderCacheKey = null;

        onWillStart(async () => { await this._load(); });

        onMounted(() => {
            this._mm = ev => this._onMouseMove(ev);
            this._mu = ev => this._onMouseUp(ev);
            window.addEventListener('mousemove', this._mm, { passive: false });
            window.addEventListener('mouseup',   this._mu);
            // Center on today after first render
            setTimeout(() => this.goToday(), 100);
        });

        onWillUnmount(() => {
            window.removeEventListener('mousemove', this._mm);
            window.removeEventListener('mouseup',   this._mu);
            if (this._raf) cancelAnimationFrame(this._raf);
        });
    }

    setZoom(val) {
        this.st.zoom = val;
        lsSet(LS_KEY_ZOOM, val);
        this._renderCache = null;
        setTimeout(() => this.goToday(), 50);
    }

    setBarStyle(val) {
        this.st.barStyle = val;
        lsSet(LS_KEY_STYLE, val);
        this._renderCache = null;
    }

    // ── Data Loading (optimized) ───────────────────────────────────────────
    async _load() {
        this.st.loading = true;
        this.st.error   = null;

        // === VACIADO TEMPORAL =================================================
        // El planner se alimentará desde otra fuente de datos. Mientras tanto no
        // consultamos control.pedido(.line): dejamos las tareas vacías para que
        // la vista cargue sin leer registros. La UI queda intacta.
        // Para reconectar: borra este bloque hasta el `return`.
        this.st.tasks     = [];
        this._renderCache = null;
        this.st.loading   = false;
        return;
        // === FIN VACIADO TEMPORAL (código original intacto debajo) ============

        try {
            const selIds = this.st.selIds || [];
            if (!selIds.length) {
                this.st.tasks = [];
                this._renderCache = null;
                return;
            }
            const domain = [['id', 'in', selIds]];

            // ① Lines — first query (gateway to get IDs for parallel queries below)
            const lines = await this.orm.searchRead(
                'control.pedido.line',
                domain,
                ['id', 'batch', 'customer', 'area', 'start_date', 'end_date',
                 'wish_date', 'state', 'pedido_id', 'next_process', 'description',
                 'colorcode', 'colorname'],
                { limit: 500, order: 'start_date desc' }
            );

            if (!lines.length) {
                this.st.tasks = [];
                this._renderCache = null;
                return;
            }

            const parentIds = [...new Set(lines.map(l => l.pedido_id?.[0]).filter(Boolean))];
            const lineIds   = lines.map(l => l.id);

            // ② Parents + proceso counts — in parallel (the key speedup)
            // For proceso: only fetch the 2 fields we need (id + completion flag)
            const [parents, procesos] = await Promise.all([
                parentIds.length
                    ? this.orm.searchRead(
                        'control.pedido',
                        [['id', 'in', parentIds]],
                        ['id', 'numordped', 'state', 'fecha', 'fecoc', 'wish_date', 'user_id']
                      )
                    : Promise.resolve([]),
                lineIds.length
                    ? this.orm.searchRead(
                        'control.proceso.lines',
                        [['pedido_line_id', 'in', lineIds]],
                        ['pedido_line_id', 'barFasDTF'],   // minimal — just need count + done flag
                        { limit: lineIds.length * 50 }     // generous cap: 50 steps per line max
                      )
                    : Promise.resolve([]),
            ]);

            // Build lookup maps
            const parentMap = new Map(parents.map(p => [p.id, p]));

            // Aggregate counts in JS (faster than extra DB round-trip)
            const countMap = new Map();
            for (const p of procesos) {
                const lid = p.pedido_line_id[0];
                let c = countMap.get(lid);
                if (!c) { c = { total: 0, done: 0 }; countMap.set(lid, c); }
                c.total++;
                if (p.barFasDTF) c.done++;
            }

            const today = this.today;
            this.st.tasks = lines.map(line => {
                const parent     = parentMap.get(line.pedido_id?.[0]);
                const parentStart = parent ? parseDate(parent.fecha || parent.fecoc) : null;
                const parentEnd   = parent ? parseDate(parent.wish_date) : null;

                const start = parseDate(line.start_date) || parentStart || today;
                // Records without end date get a 30-day default so they're draggable
                const end   = parseDate(line.end_date)   || parseDate(line.wish_date)
                            || parentEnd || (start + 30 * DAY_MS);

                const counts   = countMap.get(line.id) || { total: 0, done: 0 };
                const progress = line.state === 'completed'
                    ? 100
                    : (counts.total > 0 ? (counts.done / counts.total) * 100 : 0);

                const area = (line.area || 'SIN ÁREA').toUpperCase().trim();

                // Color label: "code – name" or just one of them
                const colorParts = [line.colorcode, line.colorname].filter(Boolean);
                const color = colorParts.join(' – ') || '';

                const op      = parent?.numordped || '';
                const voucher = line.batch || '';

                return {
                    id:          line.id,
                    op,
                    voucher,
                    // barLabel uses voucher + progress
                    code:        voucher || op || 'S/C',
                    client:      line.customer || '–',
                    articulo:    line.description || '–',
                    color,
                    area,
                    start,
                    end,
                    hasDate:     !!(line.start_date || line.end_date || line.wish_date),
                    progress,
                    nextProcess: line.next_process || '–',
                    state:       parent?.state || 'on',
                };
            });

            this._renderCache = null; // invalidate so render recomputes
        } catch (e) {
            this.st.error = 'Error al cargar los pedidos.';
            console.error('[Planner] load error:', e);
        } finally {
            this.st.loading = false;
        }
    }

    // ── Render (memoized) ──────────────────────────────────────────────────
    // Cache key: zoom + barStyle + task count + earliest start + latest end.
    // Drag updates task.start/end directly in st.tasks — we intentionally
    // don't invalidate cache on those changes so drag doesn't trigger full recompute.
    get render() {
        const tasks = this.st.tasks;
        const cacheKey = `${this.st.zoom}|${this.st.barStyle}|${tasks.length}`;

        if (this._renderCache && this._renderCacheKey === cacheKey) {
            return this._renderCache;
        }

        const result = this._computeRender(tasks, this.st.zoom, this.st.barStyle);
        this._renderCache    = result;
        this._renderCacheKey = cacheKey;
        return result;
    }

    _computeRender(tasks, zoom, barStyle) {
        const today = this.today;
        let min = Infinity, max = -Infinity;
        for (const t of tasks) {
            if (t.start < min) min = t.start;
            if (t.end   > max) max = t.end;
        }
        if (!isFinite(min)) { min = today; max = today + 90 * DAY_MS; }

        // Always include today in the range
        if (today < min) min = today;
        if (today > max) max = today;

        // Guarantee a minimum visible span per zoom level
        const minSpanMs = { horas: 3 * DAY_MS, dias: 30 * DAY_MS, semanas: 90 * DAY_MS, meses: 365 * DAY_MS, anios: 3 * 365 * DAY_MS };
        const zoomKey   = zoom === 'años' ? 'anios' : zoom;
        const minSpan   = minSpanMs[zoomKey] || 30 * DAY_MS;
        if ((max - min) < minSpan) max = min + minSpan;

        // ── Time range boundaries ──────────────────────────────────────────
        let rs, re;
        if (zoom === 'horas') {
            rs = sod(min) - DAY_MS;
            re = sod(max) + 2 * DAY_MS;
        } else if (zoom === 'dias') {
            rs = sod(min) - 2 * DAY_MS;
            re = sod(max) + 3 * DAY_MS;
        } else if (zoom === 'semanas') {
            rs = sow(min) - 7  * DAY_MS;
            re = sow(max) + 14 * DAY_MS;
        } else if (zoom === 'meses') {
            rs = addMonths(som(min), -1);
            re = addMonths(som(max),  2);
        } else {
            rs = addYears(soy(min), -1);
            re = addYears(soy(max),  2);
        }

        // ── px/ms ratio ────────────────────────────────────────────────────
        const dayPxMap = { horas: 672, dias: 54, semanas: 16, meses: 5.2, anios: 1.1 };
        const dayPx    = dayPxMap[zoomKey] || dayPxMap.dias;
        const pxPerMs  = dayPx / DAY_MS;
        const totalWidth = (re - rs) * pxPerMs;
        const xOf = ms => (ms - rs) * pxPerMs;


        // ── Tick & grid generation ─────────────────────────────────────────
        const topTicks    = [];
        const bottomTicks = [];
        const gridLines   = [];
        const weekendBands = [];

        if (zoom === 'horas') {
            const hourPx = dayPx / 24;
            for (let d = rs; d < re; d += DAY_MS) {
                const dt = new Date(d);
                topTicks.push({ x: xOf(d), w: DAY_MS * pxPerMs, label: DOW[dt.getDay()] + ' ' + dt.getDate() + ' ' + MONTHS[dt.getMonth()] });
                gridLines.push({ x: xOf(d), color: 'var(--plr-grid-strong)' });
                if (isWeekend(d)) weekendBands.push({ x: xOf(d), w: DAY_MS * pxPerMs });
            }
            for (let h = rs; h < re; h += 3 * 3600000) {
                const dt = new Date(h);
                bottomTicks.push({ x: xOf(h), w: 3 * hourPx, label: pad2(dt.getHours()) + ':00', color: isWeekend(h) ? 'var(--plr-muted4)' : 'var(--plr-text3)' });
            }
        } else if (zoom === 'dias') {
            for (let d = rs; d < re; d += DAY_MS) {
                const dt = new Date(d);
                bottomTicks.push({ x: xOf(d), w: dayPx, label: DOW_SHORT[dt.getDay()] + ' ' + dt.getDate(), color: isWeekend(d) ? 'var(--plr-muted4)' : 'var(--plr-text3)' });
                gridLines.push({ x: xOf(d), color: dt.getDay() === 1 ? 'var(--plr-grid-strong)' : 'var(--plr-border2)' });
                if (isWeekend(d)) weekendBands.push({ x: xOf(d), w: dayPx });
            }
            for (let mc = som(rs); mc < re; mc = addMonths(mc, 1)) {
                const next = addMonths(mc, 1);
                topTicks.push({ x: Math.max(0, xOf(mc)), w: Math.min(totalWidth, xOf(next)) - Math.max(0, xOf(mc)), label: MONTHS_FULL[new Date(mc).getMonth()] + ' ' + new Date(mc).getFullYear() });
            }
        } else if (zoom === 'semanas') {
            for (let w = rs; w < re; w += 7 * DAY_MS) {
                const dt = new Date(w);
                bottomTicks.push({ x: xOf(w), w: 7 * dayPx, label: 'Sem · ' + dt.getDate() + ' ' + MONTHS[dt.getMonth()], color: 'var(--plr-text3)' });
                gridLines.push({ x: xOf(w), color: 'var(--plr-grid-strong)' });
            }
            for (let mc = som(rs); mc < re; mc = addMonths(mc, 1)) {
                const next = addMonths(mc, 1);
                topTicks.push({ x: Math.max(0, xOf(mc)), w: Math.min(totalWidth, xOf(next)) - Math.max(0, xOf(mc)), label: MONTHS_FULL[new Date(mc).getMonth()] + ' ' + new Date(mc).getFullYear() });
            }
        } else if (zoom === 'meses') {
            for (let mc = som(rs); mc < re; mc = addMonths(mc, 1)) {
                const next = addMonths(mc, 1);
                const dt   = new Date(mc);
                bottomTicks.push({ x: xOf(mc), w: (next - mc) * pxPerMs, label: MONTHS[dt.getMonth()], color: 'var(--plr-text3)' });
                gridLines.push({ x: xOf(mc), color: dt.getMonth() === 0 ? 'var(--plr-grid-strong)' : 'var(--plr-border2)' });
            }
            for (let yc = soy(rs); yc < re; yc = addYears(yc, 1)) {
                const next = addYears(yc, 1);
                topTicks.push({ x: Math.max(0, xOf(yc)), w: Math.min(totalWidth, xOf(next)) - Math.max(0, xOf(yc)), label: '' + new Date(yc).getFullYear() });
            }
        } else {
            for (let yc = soy(rs); yc < re; yc = addYears(yc, 1)) {
                const next = addYears(yc, 1);
                bottomTicks.push({ x: xOf(yc), w: (next - yc) * pxPerMs, label: '' + new Date(yc).getFullYear(), color: 'var(--plr-text3)' });
                gridLines.push({ x: xOf(yc), color: 'var(--plr-grid-strong)' });
            }
        }

        // ── Layout constants ───────────────────────────────────────────────
        const sidebarW = 300;
        const headerH  = 58;
        const rowH     = 62;
        const barH     = 28;
        const barTop   = Math.round((rowH - barH) / 2);
        const dateTop  = barTop + Math.round((barH - 12) / 2);

        // ── Group tasks by area (include ALL areas from data) ──────────────
        const uniqueAreasSet = new Set(tasks.map(t => t.area || 'SIN ÁREA'));
        const activeAreas = [
            ...AREA_ORDER.filter(a => uniqueAreasSet.has(a)),
            ...[...uniqueAreasSet].filter(a => !AREA_ORDER.includes(a)).sort(),
        ];
        if (!activeAreas.length) activeAreas.push('SIN ÁREA');

        const rows = [];
        for (const area of activeAreas) {
            const am   = areaMeta(area);
            const list = tasks
                .filter(t => (t.area || 'SIN ÁREA') === area)
                .sort((a, b) => a.start - b.start);
            if (!list.length) continue;

            rows.push({
                isSection: true, isTask: false,
                h: rowH, area,
                color: am.color, soft: am.soft,
                count: list.length + (list.length === 1 ? ' partida' : ' partidas'),
            });

            for (const t of list) {
                const sm    = statusMeta(t.end, t.progress, today);
                const x     = xOf(t.start);
                const w     = Math.max(10, (t.end - t.start) * pxPerMs);
                const fillW = Math.max(0, w * Math.min(100, t.progress) / 100);

                let barBg, fillBg, barTextColor;
                if (barStyle === 'avance') {
                    barBg = 'var(--plr-bar-track)'; fillBg = sm.color; barTextColor = 'var(--plr-text2b)';
                } else if (barStyle === 'area') {
                    barBg = am.color; fillBg = 'var(--plr-bar-fill-overlay)'; barTextColor = '#fff';
                } else {
                    barBg = sm.color; fillBg = 'var(--plr-bar-fill-overlay)'; barTextColor = '#fff';
                }

                const dateLabel = t.hasDate
                    ? formatShort(t.start) + ' – ' + formatShort(t.end)
                    : 'Sin fecha';
                rows.push({
                    isSection: false, isTask: true,
                    h: rowH, id: t.id,
                    op: t.op, voucher: t.voucher,
                    client: t.client, articulo: t.articulo, color: t.color,
                    areaColor: am.color, soft: am.soft,
                    statusColor: sm.color, statusLabel: sm.label,
                    x, w, fillW, barTop, barH, barBg, fillBg, barTextColor,
                    barLabel: (t.voucher || t.op || 'S/C') + ' · ' + Math.round(t.progress) + '%',
                    dateLabel, dateX: x + w + 9, dateTop,
                    tip: [
                        t.op ? 'OP ' + t.op : '',
                        t.voucher ? 'Partida ' + t.voucher : '',
                        t.articulo, t.color, t.client,
                        formatShort(t.start) + ' – ' + formatShort(t.end),
                        Math.round(t.progress) + '%  ·  ' + sm.label,
                    ].filter(Boolean).join('  |  '),
                    start: t.start, end: t.end,
                });
            }
        }

        return {
            sidebarW, headerH, totalWidth,
            totalGridWidth: sidebarW + totalWidth,
            topTicks, bottomTicks, gridLines, weekendBands,
            todayX: xOf(today),
            todayInRange: today >= rs && today <= re,
            rangeLabel: formatShort(rs) + '  →  ' + formatShort(re),
            rows,
            // Geometry exposed so event handlers (goToday, drag) read the SAME
            // values the view was rendered with — never instance side-effects,
            // which don't survive OWL's render-proxy → raw-`this` boundary.
            rs, pxPerMs,
        };
    }

    // ── Drag & Drop (RAF-throttled, no reactive state during drag) ─────────
    onBarMouseDown(row, mode, ev) {
        if (ev.button !== 0) return;
        ev.preventDefault();
        ev.stopPropagation();

        // Record original bar geometry from DOM to survive any prior cached positions
        const barEl     = ev.currentTarget.classList.contains('plr__bar')
            ? ev.currentTarget
            : ev.currentTarget.closest('.plr__bar');
        const origBarX  = barEl ? parseFloat(barEl.style.left) || row.x : row.x;
        const origBarW  = barEl ? parseFloat(barEl.style.width) || row.w : row.w;

        this.drag = {
            id: row.id, mode,
            startX: ev.clientX,
            os: row.start, oe: row.end,
            origBarX, origBarW,
            // Capture the scale now; this.pxPerMs side-effect is unreliable.
            pxPerMs: this.render.pxPerMs,
            deltaMs: 0,
        };
        document.body.style.cursor    = mode === 'move' ? 'grabbing' : 'ew-resize';
        document.body.style.userSelect = 'none';
    }

    _onMouseMove(ev) {
        if (!this.drag) return;
        if (this._raf) return;          // already queued — skip this event
        ev.preventDefault();
        const clientX = ev.clientX;
        this._raf = requestAnimationFrame(() => {
            this._raf = null;
            if (!this.drag) return;

            const d    = this.drag;
            const snap = this.st.zoom === 'horas' ? 3600000 : DAY_MS;
            let dms    = (clientX - d.startX) / d.pxPerMs;
            dms        = Math.round(dms / snap) * snap;
            d.deltaMs  = dms;

            // Move the bar imperatively in the DOM — zero re-renders during drag
            const bodyEl = this.scrollRef.el;
            const rowEl  = bodyEl && bodyEl.querySelector(`[data-row-id="${d.id}"]`);
            const barEl  = rowEl && rowEl.querySelector('.plr__bar');
            if (!barEl) return;

            const dpx = dms * d.pxPerMs;
            if (d.mode === 'move') {
                barEl.style.left  = Math.round(d.origBarX + dpx) + 'px';
            } else if (d.mode === 'l') {
                const clampedDpx  = Math.min(dpx, d.origBarW - 10);
                barEl.style.left  = Math.round(d.origBarX + clampedDpx) + 'px';
                barEl.style.width = Math.max(10, Math.round(d.origBarW - clampedDpx)) + 'px';
            } else {
                barEl.style.width = Math.max(10, Math.round(d.origBarW + dpx)) + 'px';
            }
        });
    }

    async _onMouseUp(ev) {
        if (!this.drag) return;
        const d = this.drag;
        this.drag = null;
        if (this._raf) { cancelAnimationFrame(this._raf); this._raf = null; }
        document.body.style.cursor     = '';
        document.body.style.userSelect = '';

        const dms = d.deltaMs;
        if (!dms) return; // no movement

        const snap = this.st.zoom === 'horas' ? 3600000 : DAY_MS;
        let ns = d.os, ne = d.oe;
        if (d.mode === 'move') {
            ns = d.os + dms; ne = d.oe + dms;
        } else if (d.mode === 'l') {
            ns = Math.min(d.os + dms, d.oe - snap);
        } else {
            ne = Math.max(d.oe + dms, d.os + snap);
        }

        // Update reactive task state and invalidate render cache
        const task = this.st.tasks.find(t => t.id === d.id);
        if (task) { task.start = ns; task.end = ne; }
        this._renderCache = null;

        try {
            await this.orm.write('control.pedido.line', [d.id], {
                start_date: dateToOdooStr(ns),
                end_date:   dateToOdooStr(ne),
            });
        } catch (err) {
            console.error('[Planner] Save error:', err);
            await this._load(); // revert on error
        }
    }

    // ── Navigation ────────────────────────────────────────────────────────
    goToday() {
        const el = this.scrollRef.el;
        if (!el) return;
        // Read geometry from the render result (same numbers the view drew with),
        // NOT from instance fields — those are written inside the render getter
        // where `this` is OWL's reactive proxy and never reach this raw handler.
        const r = this.render;
        const sidebarW = r.sidebarW;
        // Center the "today" marker inside the visible timeline area (right of
        // the sticky sidebar). x is the marker offset within the timeline.
        const x = (this.today - r.rs) * r.pxPerMs;
        const target = x - (el.clientWidth - sidebarW) / 2;
        const maxScroll = el.scrollWidth - el.clientWidth;
        el.scrollLeft = Math.max(0, Math.min(target, maxScroll));
    }

    openRecord(row) {
        this.actionService.doAction({
            type: 'ir.actions.act_window',
            res_model: 'control.pedido.line',
            res_id: row.id,
            views: [[false, 'form']],
            target: 'current',
        });
    }

    // ── Picker Modal ───────────────────────────────────────────────────────
    async openPicker() {
        this.st.picker.open    = true;
        this.st.picker.loading = true;
        this.st.picker.search  = '';

        // === VACIADO TEMPORAL: modal sin registros (nueva fuente de datos).
        // Para reconectar: borra este bloque hasta el `return`.
        this.st.picker.records = [];
        this.st.picker.checked = [];
        this.st.picker.loading = false;
        return;
        // === FIN VACIADO TEMPORAL (código original intacto debajo) ============

        try {
            const records = await this.orm.searchRead(
                'control.pedido.line',
                [],
                ['id', 'batch', 'customer', 'area', 'start_date', 'wish_date', 'pedido_id'],
                { limit: 1000, order: 'id desc' }
            );
            this.st.picker.records = records.map(r => ({
                id:       r.id,
                numordped: r.batch || (r.pedido_id && r.pedido_id[1]) || 'S/C',
                customer: r.customer || 'Sin Cliente',
                area:     (r.area || 'SIN ÁREA').toUpperCase().trim(),
                fecha:    r.start_date || r.wish_date || '',
            }));
            const currentIds = new Set(this.st.tasks.map(t => t.id));
            this.st.picker.checked = this.st.picker.records
                .filter(r => currentIds.has(r.id)).map(r => r.id);
        } catch (e) {
            console.error('[Planner] picker load error:', e);
        } finally {
            this.st.picker.loading = false;
        }
    }

    closePicker() { this.st.picker.open = false; }

    togglePick(id) {
        const arr = this.st.picker.checked;
        const idx = arr.indexOf(id);
        if (idx === -1) arr.push(id); else arr.splice(idx, 1);
    }

    isPicked(id) { return this.st.picker.checked.includes(id); }

    async applyPicker() {
        const checked = [...this.st.picker.checked];
        this.st.selIds = checked;
        lsSet(LS_KEY_SEL, checked);
        this.st.picker.open = false;
        await this._load();
        // Re-center on today once the new tasks have rendered.
        setTimeout(() => this.goToday(), 60);
    }

    async clearSelection() {
        this.st.selIds = [];
        lsSet(LS_KEY_SEL, []);
        await this._load();
    }

    get pickerFiltered() {
        const q = (this.st.picker.search || '').toLowerCase().trim();
        if (!q) return this.st.picker.records;
        return this.st.picker.records.filter(r =>
            r.numordped.toLowerCase().includes(q) ||
            r.customer.toLowerCase().includes(q)  ||
            r.area.toLowerCase().includes(q)
        );
    }

    // ── Template computed helpers ──────────────────────────────────────────
    get totalCount() { return this.st.tasks.length; }

    get selLabel() {
        const ids = this.st.selIds;
        if (!ids || !ids.length) return 'Sin selección';
        return ids.length + ' partida' + (ids.length === 1 ? '' : 's');
    }

    get zoomBtns() {
        const accent     = 'var(--plr-accent)';
        const accentSoft = 'var(--plr-accent-soft)';
        const opts = [['horas','Horas'],['dias','Días'],['semanas','Semanas'],['meses','Meses'],['anios','Años']];
        return opts.map(([key, label]) => {
            const on = key === this.st.zoom;
            return { key, label, onClick: () => this.setZoom(key),
                bc: on ? accent : 'var(--plr-btn-border)', bg: on ? accentSoft : 'var(--plr-surface)', fg: on ? accent : 'var(--plr-text2)' };
        });
    }

    get styleBtns() {
        const accent     = 'var(--plr-accent)';
        const accentSoft = 'var(--plr-accent-soft)';
        const opts = [['estado','Por estado'],['avance','Por avance'],['area','Por área']];
        return opts.map(([key, label]) => {
            const on = key === this.st.barStyle;
            return { key, label, onClick: () => this.setBarStyle(key),
                bc: on ? accent : 'var(--plr-btn-border)', bg: on ? accentSoft : 'var(--plr-surface)', fg: on ? accent : 'var(--plr-text2)' };
        });
    }
}

registry.category('actions').add('plan_alpha_planner', PlannerView);
