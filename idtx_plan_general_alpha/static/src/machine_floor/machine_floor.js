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
    MAQ:             { icon: "fa-tint",     color: "#06b6d4", bg: "#ecfeff" },
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
    "JERSERA", "LISTADORA", "RIPERA", "GAMUZA", "FELPA", "FRANELA",
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
        });

        this._dragId   = null;
        this._dragSlot = null;

        onWillStart(async () => {
            await this._loadWorkcenters();
        });
    }

    // ── Loading ──────────────────────────────────────────────────────────────

    async _loadWorkcenters() {
        this.state.loading = true;
        try {
            const data = await rpc("/idtx_plan_alpha/workcenters", {});
            this.state.workcenters = data.workcenters || [];
            if (this.state.workcenters.length) {
                await this._loadMachines(this.state.workcenters[0].name);
            }
        } catch (e) {
            console.error("[MachineFloor] Error cargando centros de trabajo:", e);
        } finally {
            this.state.loading = false;
        }
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

    // Full slot grid (no filter): ALL slots including empties, for DnD
    get gridSlots() {
        const ms = this.state.machines;
        const maxSlot = ms.length ? Math.max(...ms.map(m => m.slot_index)) : -1;
        const minSlots = (Math.ceil((ms.length + 1) / GRID_COLS) + GRID_EXTRA_ROWS) * GRID_COLS;
        const total = Math.max(
            minSlots,
            (Math.ceil((maxSlot + 1) / GRID_COLS) + GRID_EXTRA_ROWS) * GRID_COLS
        );
        const bySlot = new Map(ms.map(m => [m.slot_index, m]));
        return Array.from({ length: total }, (_, i) => {
            const raw = bySlot.get(i) || null;
            return { index: i, machine: raw ? enrich(raw) : null };
        });
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

    // ── Drag & Drop ───────────────────────────────────────────────────────────

    onMachineDragStart(ev) {
        const card = ev.currentTarget;
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
        ev.currentTarget.classList.remove("mf-slot--over");

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
            machines[targetIdx].slot_index = fromSlot;
            this._savePosition(machines[targetIdx].id, fromSlot);
        }

        machines[draggedIdx].slot_index = targetSlot;
        this.state.machines = machines;
        this._savePosition(dragId, targetSlot);
    }

    async _savePosition(machineId, slotIndex) {
        try {
            await rpc("/idtx_plan_alpha/save_floor_position", {
                equipment_id: machineId,
                workcenter:   this.state.activeWc,
                slot_index:   slotIndex,
            });
        } catch (e) {
            console.error("[MachineFloor] Error guardando posición:", e);
        }
    }
}

registry.category("actions").add("idtx_plan_alpha.MachineFloor", MachineFloor);
