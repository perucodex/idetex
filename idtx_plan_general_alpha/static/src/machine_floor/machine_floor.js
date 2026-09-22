/** @odoo-module **/

import { Component, useState, useRef, onWillStart, onMounted, onPatched, onWillUnmount } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { rpc } from "@web/core/network/rpc";

// Ancho de codificación de la cuadrícula: slot_index = row*GRID_COLS + col.
// Este valor queda fijo para siempre una vez que hay máquinas guardadas
// (cambiarlo reinterpretaría mal las posiciones ya guardadas) — por eso es
// generoso, muy por encima de lo que se necesita visualmente hoy.
const GRID_COLS = 60;
// Ancho VISIBLE por defecto (lo que se ve sin que ninguna máquina lo pase).
const GRID_MIN_COLS = 24;
// Columnas vacías de margen que se muestran de más, a la derecha del último
// cuadro ocupado — mismo rol que GRID_EXTRA_ROWS pero en horizontal.
const GRID_EXTRA_COLS = 2;
const GRID_EXTRA_ROWS = 2;
// Mirrors .mf-grid-inner's CSS (gap + padding) and .mf-slot's fixed size —
// needed in JS to convert a mouse drag (px) into a number of grid cells.
// El ancho de columna es FIJO (no 1fr): así, al revelar columnas extra a la
// derecha, las que ya existen nunca cambian de tamaño ni se corren — la
// cuadrícula solo se hace más ancha (con scroll horizontal si hace falta).
// Con 1fr, agregar columnas angostaba TODAS las existentes, corriéndolas
// justo debajo del cursor en el momento de soltar — eso hacía que la
// máquina cayera en la columna nueva sin querer.
const GRID_GAP_PX     = 4;
const GRID_PAD_X_PX   = 10;
const SLOT_HEIGHT_PX  = 70;
// Ancho MÍNIMO de columna — nunca más chico que esto. El ancho REAL usado
// (state.cellWidthPx, ver _measureCellWidth) se calcula en base al ancho de
// reposo (_restingCols) para llenar el espacio disponible, como antes con
// 1fr — pero es un número fijo en px, no una fracción, así que agregar
// columnas de margen nunca reduce el tamaño de las que ya existen.
const SLOT_WIDTH_MIN_PX = 70;

const TYPE_CONFIG = {
    JERSERA:         { icon: "fa-th",       color: "#3b82f6", bg: "#eff6ff" },
    LISTADORA:       { icon: "fa-list-ol",  color: "#8b5cf6", bg: "#f5f3ff" },
    RIPERA:          { icon: "fa-scissors", color: "#f97316", bg: "#fff7ed" },
    GAMUZA:          { icon: "fa-circle-o", color: "#14b8a6", bg: "#f0fdfa" },
    FELPA:           { icon: "fa-th-large", color: "#ec4899", bg: "#fdf2f8" },
    FRANELA:         { icon: "fa-bars",     color: "#eab308", bg: "#fefce8" },
    TEÑIDORA:        { icon: "fa-tint",     color: "#0891b2", bg: "#ecfeff" },
    MAQ:             { icon: "fa-cog",      color: "#06b6d4", bg: "#ecfeff" },
    BIANCALANI:      { icon: "fa-refresh",  color: "#10b981", bg: "#f0fdf4" },
    ABRIDORA:        { icon: "fa-expand",   color: "#6366f1", bg: "#eef2ff" },
    HIDROEXTRACTORA: { icon: "fa-compress", color: "#64748b", bg: "#f8fafc" },
    TERMOFIJADO:     { icon: "fa-fire",     color: "#ef4444", bg: "#fef2f2" },
};

// One color per workcenter (cycles if more than 8)
const WC_COLORS = [
    ["#1e40af", "#3b82f6"],  // blue
    ["#155e75", "#0891b2"],  // cyan
    ["#5b21b6", "#7c3aed"],  // violet
    ["#166534", "#16a34a"],  // green
    ["#9a3412", "#ea580c"],  // orange
    ["#7f1d1d", "#dc2626"],  // red
    ["#0f4c75", "#0369a1"],  // indigo
    ["#713f12", "#d97706"],  // amber
];

const TYPE_DETECT = [
    "JERSERA", "LISTADORA", "RIPERA", "GAMUZA", "FELPA", "FRANELA", "TEÑIDORA",
    "BIANCALANI", "ABRIDORA", "HIDROEXTRACTORA", "TERMOFIJADO",
];

function machineType(name) {
    const n = (name || "").toUpperCase();
    return TYPE_DETECT.find(t => n.includes(t)) || "MAQ";
}

function machineNum(name) {
    const n = (name || "").toUpperCase();
    // Prefer number right after "MAQ" (e.g. "FRANELA 3 HILOS MAQ 76" → 76)
    const maq = n.match(/MAQ\s+(\d+)/);
    if (maq) return maq[1];
    // Fallback: last number in the name
    const all = n.match(/\d+/g);
    return all ? all[all.length - 1] : "—";
}

function machineStatus(m) {
    if (m.machine_state) return m.machine_state;
    // fallback for records without machine_state
    if (m.oos)      return "malograda";
    if (!m.enabled) return "apagada";
    return "operativa";
}

function enrich(m) {
    const type   = machineType(m.name);
    const status = machineStatus(m);
    const num    = machineNum(m.name);
    const tcfg   = TYPE_CONFIG[type] || { icon: "fa-cog", color: "#94a3b8", bg: "#f8fafc" };
    return { ...m, type, status, num, tcfg };
}

// ── Combined-cell helpers ────────────────────────────────────────────────

function coveredCells(anchor, spanCols, spanRows, cols) {
    const w = spanCols || 1, h = spanRows || 1;
    const cells = [];
    for (let r = 0; r < h; r++) for (let c = 0; c < w; c++) cells.push(anchor + r * cols + c);
    return cells;
}

export class MachineFloor extends Component {
    static template = "idtx_plan_alpha.MachineFloor";
    static props = ["*"];

    setup() {
        this.state = useState({
            loading:    true,
            wcLoading:  false,
            workcenters: [],
            activeWc:   null,
            machines:   [],
            filterStatus: "all",
            filterType:   "all",
            panel: { open: false, loading: false, machine: null, tejiendo: [], historial: [] },
            // Redimensión libre en curso (arrastre desde la esquina de una
            // máquina) — null cuando no se está arrastrando. Ver
            // onResizeHandleMouseDown/_handleResizeMove/_handleResizeUp.
            resize:    null,
            // true mientras se está ARRASTRANDO (moviendo) una máquina y el
            // cursor ya pisa la última columna de reposo — ver
            // onSlotDragOver. Dispara el margen de columnas extra igual
            // que state.resize, pero para mover en vez de agrandar.
            dragPastEdge: false,
            // Ancho de columna EN PX que llena el espacio disponible del
            // panel — ver _measureCellWidth. Empieza en el mínimo hasta
            // que el contenedor real existe y se puede medir.
            cellWidthPx: SLOT_WIDTH_MIN_PX,
        });

        this.slotGridRef = useRef("slotGrid");

        this._dragId   = null;
        this._dragSlot = null;
        this._dragged  = false;
        this._dragOffsetCols = 0;
        this._dragOffsetRows = 0;
        this._resizeCtx  = null;
        this._onResizeMove = null;
        this._onResizeUp   = null;
        this._onWindowResize = () => this._measureCellWidth();

        onWillStart(async () => {
            await this._loadWorkcenters();
        });
        // Se mide tanto en el montaje inicial (onWillStart ya puede haber
        // cargado todo antes del primer render, así que el grid a veces
        // aparece de una) como en cada actualización posterior (cambio de
        // centro de trabajo, resize de la ventana, etc.) — _measureCellWidth
        // solo escribe en el estado si el valor realmente cambió, así que
        // esto converge solo (como mucho un patch extra) en vez de repetirse.
        onMounted(() => this._measureCellWidth());
        onPatched(() => this._measureCellWidth());
        window.addEventListener("resize", this._onWindowResize);
        onWillUnmount(() => {
            window.removeEventListener("resize", this._onWindowResize);
        });
    }

    // Calcula el ancho de columna que llena el espacio disponible del
    // panel, sobre el ancho de REPOSO (_restingCols) — nunca sobre
    // this.visibleCols, que puede incluir columnas de margen temporales:
    // si se calculara sobre ese, agregar el margen angostaría las columnas
    // ya existentes (el mismo problema que tenía 1fr). Nunca baja de
    // SLOT_WIDTH_MIN_PX — si no entran todas a ese tamaño, se scrollea.
    _measureCellWidth() {
        const el = this.slotGridRef.el;
        if (!el) return;
        const cols = this._restingCols;
        const available = el.clientWidth - GRID_PAD_X_PX * 2 - (cols - 1) * GRID_GAP_PX;
        const width = Math.max(SLOT_WIDTH_MIN_PX, available / cols);
        if (width !== this.state.cellWidthPx) {
            this.state.cellWidthPx = width;
        }
    }

    // ── Loading ──────────────────────────────────────────────────────────────

    async _loadWorkcenters() {
        this.state.loading = true;
        // Retry hasta 3 veces con espera creciente (resuelve race condition en tab duplicado)
        for (let attempt = 0; attempt < 3; attempt++) {
            try {
                if (attempt > 0) {
                    await new Promise(r => setTimeout(r, attempt * 600));
                }
                const data = await rpc("/idtx_plan_alpha/workcenters", {});
                this.state.workcenters = data.workcenters || [];
                if (this.state.workcenters.length) {
                    await this._loadMachines(this.state.workcenters[0].name);
                }
                break;
            } catch (e) {
                console.warn(`[MachineFloor] Intento ${attempt + 1} fallido:`, e);
                if (attempt === 2) {
                    console.error("[MachineFloor] Error cargando centros de trabajo tras 3 intentos.");
                }
            }
        }
        this.state.loading = false;
    }

    async _loadMachines(wcName) {
        this.state.wcLoading  = true;
        this.state.activeWc   = wcName;
        this.state.filterStatus = "all";
        this.state.filterType   = "all";
        try {
            const data = await rpc("/idtx_plan_alpha/floor_data", { workcenter: wcName });
            this.state.machines = data.machines || [];
        } catch (e) {
            console.error("[MachineFloor] Error cargando máquinas:", e);
            this.state.machines = [];
        } finally {
            this.state.wcLoading = false;
        }
    }

    // ── Computed getters ─────────────────────────────────────────────────────

    get activeWcColor() {
        const idx = this.state.workcenters.findIndex(w => w.name === this.state.activeWc);
        return idx >= 0 ? WC_COLORS[idx % WC_COLORS.length] : ["#334155", "#475569"];
    }

    get headerStyle() {
        const [c0, c1] = this.activeWcColor;
        return `background: linear-gradient(135deg, ${c0}, ${c1})`;
    }

    get stats() {
        const ms = this.state.machines;
        return {
            total:        ms.length,
            operativa:    ms.filter(m => machineStatus(m) === "operativa").length,
            ejecutando:   ms.filter(m => machineStatus(m) === "ejecutando").length,
            malograda:    ms.filter(m => machineStatus(m) === "malograda").length,
            mantenimiento:ms.filter(m => machineStatus(m) === "mantenimiento").length,
            apagada:      ms.filter(m => machineStatus(m) === "apagada").length,
        };
    }

    get machineTypes() {
        const seen = new Set();
        this.state.machines.forEach(m => seen.add(machineType(m.name)));
        return [...seen].sort();
    }

    get statusFilters() {
        return [
            { key: "all",          label: "Todas"        },
            { key: "operativa",    label: "Operativa"    },
            { key: "ejecutando",   label: "Ejecutando"   },
            { key: "malograda",    label: "Malograda"    },
            { key: "mantenimiento",label: "Mantenimiento"},
            { key: "apagada",      label: "Apagada"      },
        ];
    }

    get isFiltered() {
        return this.state.filterStatus !== "all" || this.state.filterType !== "all";
    }

    // Máquinas que calzan con los filtros de Estado/Tipo activos — usado
    // para el contador de la barra de filtros y para decidir, dentro de
    // gridSlots, cuáles tarjetas mostrar sin reacomodar nada.
    get filteredMachines() {
        const { filterStatus, filterType, machines } = this.state;
        return machines
            .filter(m => {
                if (filterStatus !== "all" && machineStatus(m) !== filterStatus) return false;
                if (filterType   !== "all" && machineType(m.name)  !== filterType)   return false;
                return true;
            })
            .map(enrich);
    }

    // Ancho "de reposo": SOLO hasta la última columna realmente ocupada por
    // una máquina (mínimo GRID_MIN_COLS), sin ningún margen. Es el umbral
    // ESTABLE contra el que onSlotDragOver compara la columna sobre la que
    // pasa el cursor — si en vez de esto se comparara contra
    // this.visibleCols (que ya puede incluir el margen), el propio margen
    // ya agregado desplazaría el umbral y causaría parpadeo.
    get _restingCols() {
        const ms = this.state.machines;
        let maxCol = -1;
        for (const m of ms) {
            const anchorCol = m.slot_index % GRID_COLS;
            maxCol = Math.max(maxCol, anchorCol + (m.span_cols || 1) - 1);
        }
        return Math.max(GRID_MIN_COLS, maxCol + 1);
    }

    // Cuántas columnas se muestran realmente — crece más allá del reposo
    // solo cuando hay un redimensionado o un arrastre-para-mover que ya
    // pasó la última columna visible, con un margen de GRID_EXTRA_COLS
    // celdas vacías. Nunca supera GRID_COLS (el ancho de codificación).
    // Mismo rol que el cálculo de filas, pero horizontal.
    get visibleCols() {
        // En reposo: el ancho estable, sin margen. El margen de
        // GRID_EXTRA_COLS aparece nada más mientras se está arrastrando
        // (moviendo o redimensionando) más allá de ese borde, nunca antes.
        let cols = this._restingCols;

        if (this.state.resize) {
            const r = this.state.resize;
            const rCol = Math.min(GRID_COLS - 1, r.anchorCol + r.spanCols - 1);
            if (rCol + 1 > cols) cols = rCol + 1 + GRID_EXTRA_COLS;
        }
        if (this.state.dragPastEdge) {
            cols = cols + GRID_EXTRA_COLS;
        }
        return Math.min(GRID_COLS, cols);
    }

    // Full slot grid: ALL slots including empties, for DnD. Machines with
    // span > 1 occupy multiple cells: only their anchor cell is rendered
    // (with an explicit CSS grid span); the other covered cells are skipped
    // entirely so nothing else can render on top of them.
    //
    // Con un filtro de Estado/Tipo activo, las máquinas que NO calzan se
    // ocultan (su celda se ve vacía) pero conservan su posición y tamaño
    // reales — no se reacomoda ni compacta nada, solo se esconde contenido.
    get gridSlots() {
        const ms = this.state.machines;
        const filterActive = this.isFiltered;
        const matchingIds = filterActive ? new Set(this.filteredMachines.map(m => m.id)) : null;
        const visibleCols = this.visibleCols;
        const footprints = ms.map(m =>
            coveredCells(m.slot_index, m.span_cols || 1, m.span_rows || 1, GRID_COLS)
        );
        let maxCovered = footprints.length ? Math.max(...footprints.flat()) : -1;
        // Mientras se arrastra la esquina de una máquina más allá del borde
        // actual de la cuadrícula, hay que reservar filas vacías extra para
        // que el rectángulo fantasma (mf-resize-ghost) tenga dónde pintarse.
        if (this.state.resize) {
            const r = this.state.resize;
            maxCovered = Math.max(maxCovered, r.anchorRow * GRID_COLS + Math.min(GRID_COLS - 1, r.anchorCol + r.spanCols - 1) + (r.spanRows - 1) * GRID_COLS);
        }
        const minSlots = (Math.ceil((ms.length + 1) / GRID_COLS) + GRID_EXTRA_ROWS) * GRID_COLS;
        const total = Math.max(
            minSlots,
            (Math.ceil((maxCovered + 1) / GRID_COLS) + GRID_EXTRA_ROWS) * GRID_COLS
        );
        const visibleRows = total / GRID_COLS;

        const covered = new Map(); // index -> anchor index (for cells that belong to a span)
        ms.forEach((m, i) => footprints[i].forEach(c => covered.set(c, m.slot_index)));

        const bySlot = new Map(ms.map(m => [m.slot_index, m]));
        const slots = [];
        for (let row = 0; row < visibleRows; row++) {
        for (let col = 0; col < visibleCols; col++) {
            const i = row * GRID_COLS + col;
            const anchorOf = covered.get(i);
            if (anchorOf !== undefined && anchorOf !== i) continue; // covered by another machine's span
            const raw = bySlot.get(i) || null;
            const visible = raw && (!filterActive || matchingIds.has(raw.id));
            const spanCols = raw ? (raw.span_cols || 1) : 1;
            const spanRows = raw ? (raw.span_rows || 1) : 1;
            let orientation = "square";
            if (spanCols === 1 && spanRows > 1) orientation = "vertical";
            else if (spanRows === 1 && spanCols > 1) orientation = "horizontal";
            slots.push({
                index: i,
                machine: visible ? enrich(raw) : null,
                spanCols, spanRows,
                span: spanCols * spanRows, // total de celdas — usado solo para escalar tipografía/ícono
                orientation, // 'vertical' | 'horizontal' | 'square' — para rotar el contenido en columnas angostas
                gridStyle: `grid-column: ${col + 1} / span ${spanCols}; grid-row: ${row + 1} / span ${spanRows};`,
            });
        }
        }
        return slots;
    }

    // ── Redimensión libre arrastrando la esquina (siempre disponible) ────────

    // Deshace la combinación de una máquina puntual — usado por el botón
    // inline de la tarjeta agrandada.
    async unmergeMachine(machine) {
        this.state.machines = this.state.machines.map(m =>
            m.id === machine.id ? { ...m, span_cols: 1, span_rows: 1 } : m
        );
        await this._savePosition(machine.id, machine.slot_index, 1, 1);
    }

    // Todas las celdas ocupadas por OTRAS máquinas (para validar que un
    // redimensionado no se superponga con nada al soltar).
    _occupiedCellsExcluding(excludeId) {
        const occupied = new Set();
        for (const m of this.state.machines) {
            if (m.id === excludeId) continue;
            for (const c of coveredCells(m.slot_index, m.span_cols || 1, m.span_rows || 1, GRID_COLS)) {
                occupied.add(c);
            }
        }
        return occupied;
    }

    // Inicia el arrastre desde la esquina inferior-derecha de una tarjeta.
    // El ancla (esquina superior-izquierda) no se mueve: solo crece/encoge
    // hacia abajo-derecha según el mouse, sin restricción de forma — se
    // ajusta a cualquier rectángulo que quepa en las celdas libres cubiertas.
    onResizeHandleMouseDown(ev, machine) {
        if (machineStatus(machine) === "ejecutando") return;
        ev.preventDefault();
        ev.stopPropagation();

        const anchorCol = machine.slot_index % GRID_COLS;
        const anchorRow = Math.floor(machine.slot_index / GRID_COLS);
        const startSpanCols = machine.span_cols || 1;
        const startSpanRows = machine.span_rows || 1;

        this._resizeCtx = {
            machineId: machine.id,
            slotIndex: machine.slot_index,
            anchorCol, anchorRow,
            startSpanCols, startSpanRows,
            startX: ev.clientX, startY: ev.clientY,
            cellW: this.state.cellWidthPx + GRID_GAP_PX,
            cellH: SLOT_HEIGHT_PX + GRID_GAP_PX,
            occupied: this._occupiedCellsExcluding(machine.id),
        };
        this.state.resize = { anchorCol, anchorRow, spanCols: startSpanCols, spanRows: startSpanRows, valid: true };

        this._onResizeMove = this._handleResizeMove.bind(this);
        this._onResizeUp   = this._handleResizeUp.bind(this);
        document.addEventListener("mousemove", this._onResizeMove);
        document.addEventListener("mouseup", this._onResizeUp);
    }

    _handleResizeMove(ev) {
        const ctx = this._resizeCtx;
        if (!ctx) return;
        const deltaCols = Math.round((ev.clientX - ctx.startX) / ctx.cellW);
        const deltaRows = Math.round((ev.clientY - ctx.startY) / ctx.cellH);

        const maxSpanCols = GRID_COLS - ctx.anchorCol; // no se puede salir de la cuadrícula a la derecha
        const spanCols = Math.min(maxSpanCols, Math.max(1, ctx.startSpanCols + deltaCols));
        const spanRows = Math.max(1, ctx.startSpanRows + deltaRows); // las filas crecen sin límite

        const targetCells = coveredCells(ctx.slotIndex, spanCols, spanRows, GRID_COLS);
        const valid = targetCells.every(c => !ctx.occupied.has(c));

        this.state.resize = { anchorCol: ctx.anchorCol, anchorRow: ctx.anchorRow, spanCols, spanRows, valid };
    }

    async _handleResizeUp() {
        document.removeEventListener("mousemove", this._onResizeMove);
        document.removeEventListener("mouseup", this._onResizeUp);
        const ctx    = this._resizeCtx;
        const result = this.state.resize;
        this._resizeCtx  = null;
        this.state.resize = null;
        if (!ctx || !result || !result.valid) return;
        if (result.spanCols === ctx.startSpanCols && result.spanRows === ctx.startSpanRows) return;

        this.state.machines = this.state.machines.map(m =>
            m.id === ctx.machineId ? { ...m, span_cols: result.spanCols, span_rows: result.spanRows } : m
        );
        await this._savePosition(ctx.machineId, ctx.slotIndex, result.spanCols, result.spanRows);
    }

    // ── Handlers ─────────────────────────────────────────────────────────────

    onWcTabClick(ev) {
        const name = ev.currentTarget.dataset.wc;
        if (name && name !== this.state.activeWc) {
            this._loadMachines(name);
        }
    }

    onFilterStatus(ev) {
        this.state.filterStatus = ev.currentTarget.dataset.status;
    }

    onFilterType(ev) {
        this.state.filterType = ev.currentTarget.dataset.type;
    }

    onClearFilters() {
        this.state.filterStatus = "all";
        this.state.filterType   = "all";
    }

    onRefresh() {
        if (this.state.activeWc) this._loadMachines(this.state.activeWc);
    }

    // Reordena TODAS las máquinas de TODOS los centros de trabajo según su
    // numeración de fábrica y deshace cualquier combinación de cuadros.
    async resetFactoryOrder() {
        const ok = window.confirm(
            "Esto reordena TODAS las máquinas de TODOS los centros de trabajo " +
            "según su numeración de fábrica, y deshace cualquier tamaño combinado. " +
            "No se puede deshacer. ¿Continuar?"
        );
        if (!ok) return;

        this.state.resize    = null;
        this.state.wcLoading = true;
        try {
            await rpc("/idtx_plan_alpha/reset_factory_order", {});
            if (this.state.activeWc) await this._loadMachines(this.state.activeWc);
        } catch (e) {
            console.error("[MachineFloor] Error reordenando de fábrica:", e);
        } finally {
            this.state.wcLoading = false;
        }
    }

    // ── Drag & Drop ───────────────────────────────────────────────────────────

    onMachineDragStart(ev) {
        const card = ev.currentTarget;
        // Una máquina EJECUTANDO no se puede mover de sitio. Las combinadas
        // (span > 1) sí se pueden arrastrar como bloque — ver onSlotDrop.
        if (card.dataset.status === "ejecutando") {
            ev.preventDefault();
            return;
        }
        this._dragId   = parseInt(card.dataset.machineId);
        this._dragSlot = parseInt(card.dataset.slot);

        // En qué celda DEL PROPIO CUADRO se hizo clic (0,0 = su esquina
        // superior-izquierda) — así al soltar, esa misma celda queda bajo
        // el cursor y el bloque se mueve entero, en vez de saltar siempre
        // a que su esquina caiga en la celda soltada.
        const spanCols = parseInt(card.dataset.spanCols || "1");
        const spanRows = parseInt(card.dataset.spanRows || "1");
        const rect = card.getBoundingClientRect();
        this._dragOffsetCols = Math.min(spanCols - 1, Math.max(0,
            Math.floor((ev.clientX - rect.left) / (rect.width / spanCols))));
        this._dragOffsetRows = Math.min(spanRows - 1, Math.max(0,
            Math.floor((ev.clientY - rect.top) / (rect.height / spanRows))));

        ev.dataTransfer.effectAllowed = "move";
        ev.dataTransfer.setData("text/plain", String(this._dragId));
        // Delay so the ghost image captures the original look
        setTimeout(() => {
            const slot = card.closest(".mf-slot");
            if (slot) slot.classList.add("mf-slot--dragging");
        }, 0);
    }

    onMachineDragEnd() {
        document.querySelectorAll(".mf-slot--dragging, .mf-slot--over")
            .forEach(el => el.classList.remove("mf-slot--dragging", "mf-slot--over"));
        this._dragId = this._dragSlot = null;
        this._dragged = true;
        this.state.dragPastEdge = false;
        setTimeout(() => { this._dragged = false; }, 200);
    }

    // ── Side panel ────────────────────────────────────────────────────────────

    async onMachineCardClick(ev) {
        if (this._dragged) return;
        const machineId = parseInt(ev.currentTarget.dataset.machineId);
        if (!machineId) return;
        this.state.panel = { open: true, loading: true, machine: null, tejiendo: [], historial: [] };
        try {
            const data = await rpc("/idtx_plan_alpha/machine_detail", { equipment_id: machineId });
            this.state.panel = { open: true, loading: false, machine: data.machine, tejiendo: data.tejiendo || [], historial: data.historial || [] };
        } catch (e) {
            console.error("[MachineFloor] Error cargando detalle:", e);
            this.state.panel = { open: true, loading: false, machine: null, tejiendo: [], historial: [] };
        }
    }

    onCloseSidePanel() {
        this.state.panel = { ...this.state.panel, open: false };
    }

    panelStateLabel(s) {
        return { operativa: "Operativa", ejecutando: "Ejecutando",
                 malograda: "Malograda", mantenimiento: "Mantenimiento",
                 apagada: "Apagada" }[s] || s || "—";
    }

    onSlotDragOver(ev) {
        ev.preventDefault();
        ev.dataTransfer.dropEffect = "move";
        ev.currentTarget.classList.add("mf-slot--over");

        // Mientras se arrastra una máquina para MOVERLA (no redimensionarla):
        // si la celda sobre la que pasa el cursor ya es la última columna
        // de reposo (o más allá, una vez revelado el margen), se muestran
        // GRID_EXTRA_COLS columnas vacías extra para poder soltarla ahí —
        // ver visibleCols. Al pasar a una celda anterior, se retrae.
        if (this._dragId != null) {
            const col = parseInt(ev.currentTarget.dataset.slot) % GRID_COLS;
            this.state.dragPastEdge = col >= this._restingCols - 1;
        }
    }

    onSlotDragLeave(ev) {
        // Only remove if leaving the slot itself (not a child)
        if (!ev.currentTarget.contains(ev.relatedTarget)) {
            ev.currentTarget.classList.remove("mf-slot--over");
        }
    }

    async onSlotDrop(ev) {
        ev.preventDefault();
        // Limpiar clases de arrastre ANTES de que OWL re-renderice el DOM
        document.querySelectorAll(".mf-slot--dragging, .mf-slot--over")
            .forEach(el => el.classList.remove("mf-slot--dragging", "mf-slot--over"));

        const dropSlot = parseInt(ev.currentTarget.dataset.slot);
        const dragId    = this._dragId;
        const fromSlot  = this._dragSlot;
        if (!dragId) return;

        const machines   = this.state.machines.map(m => ({ ...m }));
        const draggedIdx = machines.findIndex(m => m.id === dragId);
        if (draggedIdx === -1) return;
        const dragged = machines[draggedIdx];
        if (machineStatus(dragged) === "ejecutando") return;

        const spanCols = dragged.span_cols || 1;
        const spanRows = dragged.span_rows || 1;

        // La celda soltada es donde quedó el CURSOR dentro de la máquina, no
        // necesariamente su esquina — se resta el punto de agarre (capturado
        // en onMachineDragStart) para que el bloque se mueva entero.
        const dropCol = dropSlot % GRID_COLS;
        const dropRow = Math.floor(dropSlot / GRID_COLS);
        const anchorCol = Math.min(GRID_COLS - spanCols, Math.max(0, dropCol - (this._dragOffsetCols || 0)));
        const anchorRow = Math.max(0, dropRow - (this._dragOffsetRows || 0));
        const targetSlot = anchorRow * GRID_COLS + anchorCol;
        if (targetSlot === fromSlot) return;

        // Caso simple: dos máquinas de 1x1 sobre la misma celda → intercambian
        // posición, como antes.
        const targetIdx = machines.findIndex(m => m.slot_index === targetSlot);
        if (spanCols === 1 && spanRows === 1 && targetIdx !== -1) {
            const targetMachine = machines[targetIdx];
            if (machineStatus(targetMachine) === "ejecutando") return;
            if ((targetMachine.span_cols || 1) * (targetMachine.span_rows || 1) > 1) return;
            targetMachine.slot_index = fromSlot;
            this._savePosition(targetMachine.id, fromSlot,
                targetMachine.span_cols || 1, targetMachine.span_rows || 1);
            dragged.slot_index = targetSlot;
            this.state.machines = machines;
            this._savePosition(dragId, targetSlot, spanCols, spanRows);
            return;
        }

        // Caso general (la máquina arrastrada ocupa varias celdas, o el
        // destino tiene una máquina combinada): solo se mueve si TODO el
        // rectángulo de destino está libre — no hay swap posible ahí.
        const targetCells = coveredCells(targetSlot, spanCols, spanRows, GRID_COLS);
        const occupied = this._occupiedCellsExcluding(dragId);
        if (targetCells.some(c => occupied.has(c))) return;

        dragged.slot_index = targetSlot;
        this.state.machines = machines;
        this._savePosition(dragId, targetSlot, spanCols, spanRows);
    }

    async _savePosition(machineId, slotIndex, spanCols = 1, spanRows = 1) {
        try {
            await rpc("/idtx_plan_alpha/save_floor_position", {
                equipment_id: machineId,
                workcenter:   this.state.activeWc,
                slot_index:   slotIndex,
                span_cols:    spanCols,
                span_rows:    spanRows,
            });
        } catch (e) {
            console.error("[MachineFloor] Error guardando posición:", e);
        }
    }
}

registry.category("actions").add("idtx_plan_alpha.MachineFloor", MachineFloor);
