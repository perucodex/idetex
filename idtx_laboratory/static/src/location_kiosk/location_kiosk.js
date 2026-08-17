/** @odoo-module */

import { Component, onMounted, useRef, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

const AREAS = [
    { value: "calidad", label: "Calidad" },
    { value: "tintoreria", label: "Tintorería" },
    { value: "laboratorio", label: "Laboratorio" },
];

function extractRpcMessage(error, fallback) {
    const candidates = [
        error?.data?.message,
        error?.data?.arguments?.[0],
        error?.message,
    ].filter((v) => typeof v === "string" && v.trim());
    for (const raw of candidates) {
        const msg = raw
            .replace(/^Odoo Server Error\s*:?\s*/i, "")
            .replace(/^RPC_ERROR\s*:?\s*/i, "")
            .trim();
        if (msg) return msg;
    }
    return fallback;
}

export class LabLocationKiosk extends Component {
    static props = {
        action: { type: Object, optional: true },
        actionId: { type: Number, optional: true },
        className: { type: String, optional: true },
        updateActionState: { type: Function, optional: true },
        "*": true,
    };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.homeMenu = useService("home_menu");

        this.barcodeRef = useRef("barcode");
        this.drawerRef = useRef("drawer");

        this.state = useState({
            area: "",
            barcode: "",
            drawer: "",
            recipe: null,
            resolving: false,
            saving: false,
            error: "",
            recent: [],
        });

        onMounted(() => this._focus(this.barcodeRef));
    }

    get AREAS() {
        return AREAS;
    }

    get currentAreaLabel() {
        const found = AREAS.find((a) => a.value === this.state.area);
        return found ? found.label : "";
    }

    get currentAreaDrawer() {
        // Cajón ya registrado para la receta en el área activa (si lo hay).
        if (!this.state.recipe || !this.state.area) return "";
        return this.state.recipe.locations?.[this.state.area] || "";
    }

    _focus(ref) {
        setTimeout(() => {
            const el = ref?.el;
            if (el) {
                el.focus();
                if (typeof el.select === "function") el.select();
            }
        }, 30);
    }

    selectArea(area) {
        this.state.area = area;
        this.state.error = "";
        this._focus(this.barcodeRef);
    }

    onBarcodeInput(ev) {
        this.state.barcode = ev.target.value || "";
    }

    onBarcodeKeydown(ev) {
        if (ev.key === "Enter") {
            ev.preventDefault();
            this.resolveBarcode();
        }
    }

    onDrawerInput(ev) {
        this.state.drawer = ev.target.value || "";
    }

    onDrawerKeydown(ev) {
        if (ev.key === "Enter") {
            ev.preventDefault();
            this.register();
        }
    }

    clearRecipe() {
        this.state.recipe = null;
        this.state.barcode = "";
        this.state.drawer = "";
        this._focus(this.barcodeRef);
    }

    async resolveBarcode() {
        const code = (this.state.barcode || "").trim();
        if (!code) return;
        if (!this.state.area) {
            this.notification.add("Seleccione primero el área.", { type: "warning" });
            this._focusArea();
            return;
        }
        this.state.resolving = true;
        this.state.error = "";
        try {
            const payload = await this.orm.call("color.recipe.location", "kiosk_resolve", [code]);
            this.state.recipe = payload;
            this.state.drawer = "";
            this._focus(this.drawerRef);
        } catch (error) {
            this.state.recipe = null;
            this.state.error = extractRpcMessage(error, "No se pudo leer el código.");
            this.notification.add(this.state.error, { type: "danger" });
            this.state.barcode = "";
            this._focus(this.barcodeRef);
        } finally {
            this.state.resolving = false;
        }
    }

    _focusArea() {
        // Sin foco concreto; solo un recordatorio visual queda en el template.
    }

    async register() {
        if (!this.state.recipe) {
            this._focus(this.barcodeRef);
            return;
        }
        const drawer = (this.state.drawer || "").trim();
        if (!drawer) {
            this.notification.add("Escanee o indique el cajón.", { type: "warning" });
            this._focus(this.drawerRef);
            return;
        }
        this.state.saving = true;
        this.state.error = "";
        try {
            const res = await this.orm.call("color.recipe.location", "kiosk_register", [
                this.state.recipe.recipe_id,
                this.state.area,
                drawer,
            ]);
            const msg = res.replaced
                ? `${res.recipe_name} · ${res.area_label}: cajón ${res.previous_drawer} → ${res.drawer}`
                : `${res.recipe_name} · ${res.area_label}: cajón ${res.drawer}`;
            this.notification.add(msg, { type: "success" });
            this.state.recent.unshift({
                key: `${res.code}-${res.area}-${Date.now()}`,
                recipe_name: res.recipe_name,
                code: res.code,
                color_name: res.color_name,
                area_label: res.area_label,
                drawer: res.drawer,
                replaced: res.replaced,
                previous_drawer: res.previous_drawer,
            });
            if (this.state.recent.length > 15) {
                this.state.recent.pop();
            }
            this.clearRecipe();
        } catch (error) {
            this.state.error = extractRpcMessage(error, "No se pudo registrar la ubicación.");
            this.notification.add(this.state.error, { type: "danger" });
        } finally {
            this.state.saving = false;
        }
    }

    async close() {
        if (window.history.length > 1) {
            window.history.back();
            return;
        }
        await this.homeMenu.toggle();
    }
}

LabLocationKiosk.template = "idtx_laboratory.LabLocationKiosk";

registry.category("actions").add("idtx_laboratory.location_kiosk", LabLocationKiosk);
