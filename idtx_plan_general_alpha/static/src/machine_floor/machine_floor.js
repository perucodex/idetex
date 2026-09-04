/** @odoo-module **/

import { Component, useState, onWillStart } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { rpc } from "@web/core/network/rpc";

// Fixed number of columns in the slot grid
const GRID_COLS = 24;
const GRID_EXTRA_ROWS = 2;

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
// Formas válidas por cantidad de celdas — cada tamaño admite orientación
// horizontal Y vertical (ej. 2 = 2x1 en fila, o 1x2 en columna).
const ALLOWED_SHAPES = {
    1: [[1, 1]],
    2: [[2, 1], [1, 2]],
    4: [[2, 2]],
    6: [[3, 2], [2, 3]],
    8: [[4, 2], [2, 4]],
};

function coveredCells(anchor, spanCols, spanRows, cols) {
    const w = spanCols || 1, h = spanRows || 1;
    const cells = [];
    for (let r = 0; r < h; r++) for (let c = 0; c < w; c++) cells.push(anchor + r * cols + c);
    return cells;
}

// Given a set of raw slot indices the user clicked, decide if they form a
// valid rectangle to combine — en fila O en columna — para 2, 4, 6 u 8 celdas.
function shapeOf(indices, cols) {
    const uniq = [...new Set(indices)];
    const n = uniq.length;
    const shapes = ALLOWED_SHAPES[n];
    if (!shapes) return { valid: false };

    const rows = uniq.map(i => Math.floor(i / cols));
    const colsArr = uniq.map(i => i % cols);
    const minRow = Math.min(...rows), maxRow = Math.max(...rows);
    const minCol = Math.min(...colsArr), maxCol = Math.max(...colsArr);
    const width  = maxCol - minCol + 1;
    const height = maxRow - minRow + 1;
    if (!shapes.some(([w, h]) => w === width && h === height)) return { valid: false };

    const anchor = minRow * cols + minCol;
    const expected = coveredCells(anchor, width, height, cols).slice().sort((x, y) => x - y);
    const sorted = uniq.slice().sort((x, y) => x - y);
    if (sorted.length !== expected.length || !sorted.every((v, i) => v === expected[i])) {
        return { valid: false };
    }
    return { valid: true, spanCols: width, spanRows: height, anchor };
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
            editMode:  false,
            selection: [],
        });

        this._dragId   = null;
        this._dragSlot = null;
        this._dragged  = false;

        onWillStart(async () => {
            await this._loadWorkcenters();
        });
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

    // Compact mode (filters active): only matching machines, enriched
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

    // Full slot grid (no filter): ALL slots including empties, for DnD.
    // Machines with span > 1 occupy multiple cells: only their anchor cell is
    // rendered (with an explicit CSS grid span); the other covered cells are
    // skipped entirely so nothing else can render on top of them.
    get gridSlots() {
        const ms = this.state.machines;
        const footprints = ms.map(m =>
            coveredCells(m.slot_index, m.span_cols || 1, m.span_rows || 1, GRID_COLS)
        );
        const maxCovered = footprints.length ? Math.max(...footprints.flat()) : -1;
        const minSlots = (Math.ceil((ms.length + 1) / GRID_COLS) + GRID_EXTRA_ROWS) * GRID_COLS;
        const total = Math.max(
            minSlots,
            (Math.ceil((maxCovered + 1) / GRID_COLS) + GRID_EXTRA_ROWS) * GRID_COLS
        );

        const covered = new Map(); // index -> anchor index (for cells that belong to a span)
        ms.forEach((m, i) => footprints[i].forEach(c => covered.set(c, m.slot_index)));

        const bySlot = new Map(ms.map(m => [m.slot_index, m]));
        const selection = this.state.selection;
        const slots = [];
        for (let i = 0; i < total; i++) {
            const anchorOf = covered.get(i);
            if (anchorOf !== undefined && anchorOf !== i) continue; // covered by another machine's span
            const raw = bySlot.get(i) || null;
            const spanCols = raw ? (raw.span_cols || 1) : 1;
            const spanRows = raw ? (raw.span_rows || 1) : 1;
            const row = Math.floor(i / GRID_COLS);
            const col = i % GRID_COLS;
            let orientation = "square";
            if (spanCols === 1 && spanRows > 1) orientation = "vertical";
            else if (spanRows === 1 && spanCols > 1) orientation = "horizontal";
            slots.push({
                index: i,
                machine: raw ? enrich(raw) : null,
                spanCols, spanRows,
                span: spanCols * spanRows, // total de celdas — usado solo para escalar tipografía/ícono
                orientation, // 'vertical' | 'horizontal' | 'square' — para rotar el contenido en columnas angostas
                gridStyle: `grid-column: ${col + 1} / span ${spanCols}; grid-row: ${row + 1} / span ${spanRows};`,
                selected: selection.includes(i),
            });
        }
        return slots;
    }

    // ── Edit mode: combine 2, 4, 6 u 8 celdas adyacentes (fila o columna) ────
    get editAction() {
        const sel = this.state.selection;
        if (!sel.length) return null;
        const ms = this.state.machines;
        const inSel = sel.map(i => ms.find(m => m.slot_index === i)).filter(Boolean);
        const isBig = m => (m.span_cols || 1) * (m.span_rows || 1) > 1;

        if (sel.length === 1) {
            const m = inSel[0];
            if (m && isBig(m)) return { type: "unmerge", machine: m };
            return null;
        }
        if (inSel.some(isBig)) {
            return { type: "invalid", message: "Deshaz la combinación existente antes de crear una nueva." };
        }
        if (inSel.length > 1) {
            return { type: "invalid", message: "Solo puedes combinar celdas con UNA máquina adentro." };
        }
        if (inSel.length === 0) {
            return { type: "invalid", message: "Selecciona una celda que tenga una máquina." };
        }
        const shape = shapeOf(sel, GRID_COLS);
        if (!shape.valid) {
            return {
                type: "invalid",
                message: "Forma inválida: elige 2, 4, 6 u 8 celdas formando un rectángulo, en fila o en columna.",
            };
        }
        return {
            type: "combine", spanCols: shape.spanCols, spanRows: shape.spanRows,
            anchor: shape.anchor, machine: inSel[0],
        };
    }

    toggleEditMode() {
        this.state.editMode = !this.state.editMode;
        this.state.selection = [];
        if (this.state.editMode) this.onClearFilters();
    }

    onSlotContainerClick(ev) {
        if (!this.state.editMode) return;
        const index = parseInt(ev.currentTarget.dataset.slot);
        const sel = this.state.selection;
        const pos = sel.indexOf(index);
        if (pos !== -1) {
            sel.splice(pos, 1);
        } else {
            if (sel.length >= 8) return;
            sel.push(index);
        }
    }

    async combineSelection() {
        const action = this.editAction;
        if (!action || action.type !== "combine") return;
        const { anchor, spanCols, spanRows, machine } = action;
        this.state.machines = this.state.machines.map(m =>
            m.id === machine.id ? { ...m, slot_index: anchor, span_cols: spanCols, span_rows: spanRows } : m
        );
        this.state.selection = [];
        await this._savePosition(machine.id, anchor, spanCols, spanRows);
    }

    async unmergeSelection() {
        const action = this.editAction;
        if (!action || action.type !== "unmerge") return;
        await this.unmergeMachine(action.machine);
    }

    // Deshace la combinación de una máquina puntual — usado por el botón
    // inline de la tarjeta agrandada, sin depender de la selección actual.
    async unmergeMachine(machine) {
        this.state.machines = this.state.machines.map(m =>
            m.id === machine.id ? { ...m, span_cols: 1, span_rows: 1 } : m
        );
        this.state.selection = this.state.selection.filter(i => i !== machine.slot_index);
        await this._savePosition(machine.id, machine.slot_index, 1, 1);
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
            "según su numeración de fábrica, y deshace cualquier combinación de " +
            "cuadros (2/4/6/8). No se puede deshacer. ¿Continuar?"
        );
        if (!ok) return;

        this.state.editMode  = false;
        this.state.selection = [];
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
        // Una máquina EJECUTANDO no se puede mover de sitio. Una máquina
        // combinada (span > 1) tampoco: deshazla primero para moverla.
        if (card.dataset.status === "ejecutando" || this.state.editMode || parseInt(card.dataset.span || "1") > 1) {
            ev.preventDefault();
            return;
        }
        this._dragId   = parseInt(card.dataset.machineId);
        this._dragSlot = parseInt(card.dataset.slot);
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
        setTimeout(() => { this._dragged = false; }, 200);
    }

    // ── Side panel ────────────────────────────────────────────────────────────

    async onMachineCardClick(ev) {
        // En modo edición, el clic lo maneja onSlotContainerClick (selección).
        if (this.state.editMode) return;
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

        const targetSlot = parseInt(ev.currentTarget.dataset.slot);
        const dragId     = this._dragId;
        const fromSlot   = this._dragSlot;

        if (!dragId || targetSlot === fromSlot) return;

        const machines   = this.state.machines.map(m => ({ ...m }));
        const draggedIdx = machines.findIndex(m => m.id === dragId);
        if (draggedIdx === -1) return;

        // Swap positions if target slot is occupied
        const targetIdx = machines.findIndex(m => m.slot_index === targetSlot);
        if (targetIdx !== -1) {
            // Una máquina EJECUTANDO no puede ser desplazada de su sitio, y una
            // combinada (span > 1x1) tampoco puede recibir un swap de 1 celda.
            if (machineStatus(machines[targetIdx]) === "ejecutando") return;
            if ((machines[targetIdx].span_cols || 1) * (machines[targetIdx].span_rows || 1) > 1) return;
            machines[targetIdx].slot_index = fromSlot;
            this._savePosition(machines[targetIdx].id, fromSlot,
                machines[targetIdx].span_cols || 1, machines[targetIdx].span_rows || 1);
        }

        machines[draggedIdx].slot_index = targetSlot;
        this.state.machines = machines;
        this._savePosition(dragId, targetSlot,
            machines[draggedIdx].span_cols || 1, machines[draggedIdx].span_rows || 1);
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
