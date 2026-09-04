/** @odoo-module */

import { Component, onWillStart, onMounted, onWillUnmount, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

const DRAFT_STORAGE_KEY = "idtx_quality_control.tone_screen.draft.v1";

function safeJsonParse(value) {
    try {
        return JSON.parse(value);
    } catch {
        return null;
    }
}

function normalizeText(value) {
    return (value || "").toString().toLowerCase().trim();
}

export class QualityToneScreen extends Component {
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
        this._searchTimer = null;

        this.state = useState({
            loading: true,
            submitting: false,
            error: "",

            partidas: [],
            partidaQuery: "",
            isSearchingPartida: false,
            showPartidaDropdown: false,

            selectedPartidaIds: [],
            selectedPartidas: [],
            inEvaluation: false,

            tonoContext: null,
            selectedMode: "",
            receta: "",
            receta_tono: "",
            recetaTachoMode: "same",
            motivo_tono: false,
            motivo_tacto: false,
            motivo_apariencia: false,
        });

        onWillStart(async () => {
            this._restoreDraft();
            await this.loadPartidas();
            this._syncSelectedPartidas();
            if (this.state.selectedPartidaIds.length) {
                await this.loadTonoContext();
            }
        });

        onMounted(() => {
            this._beforeUnloadHandler = () => this._saveDraft();
            window.addEventListener("beforeunload", this._beforeUnloadHandler);

            this._docClickHandler = (ev) => {
                const root = this.el;
                if (!root) return;
                if (!root.contains(ev.target)) {
                    this.state.showPartidaDropdown = false;
                    this._saveDraft();
                }
            };
            document.addEventListener("click", this._docClickHandler, { capture: true });
        });

        onWillUnmount(() => {
            if (this._beforeUnloadHandler) {
                window.removeEventListener("beforeunload", this._beforeUnloadHandler);
            }
            if (this._docClickHandler) {
                document.removeEventListener("click", this._docClickHandler, { capture: true });
            }
            this._saveDraft();
        });
    }

    _saveDraft() {
        const draft = {
            partidaQuery: this.state.partidaQuery || "",
            selectedPartidaIds: (this.state.selectedPartidaIds || []).map((id) => String(id)),
            showPartidaDropdown: Boolean(this.state.showPartidaDropdown),
        };
        try {
            window.localStorage.setItem(DRAFT_STORAGE_KEY, JSON.stringify(draft));
        } catch {
            // ignore
        }
    }

    _restoreDraft() {
        const raw = window.localStorage.getItem(DRAFT_STORAGE_KEY);
        if (!raw) return;

        const draft = safeJsonParse(raw);
        if (!draft || typeof draft !== "object") return;

        this.state.partidaQuery = typeof draft.partidaQuery === "string" ? draft.partidaQuery : "";
        this.state.selectedPartidaIds = Array.isArray(draft.selectedPartidaIds)
            ? draft.selectedPartidaIds.map((id) => String(id))
            : [];
        this.state.showPartidaDropdown =
            Boolean(draft.showPartidaDropdown);
    }

    _clearDraft() {
        try {
            window.localStorage.removeItem(DRAFT_STORAGE_KEY);
        } catch {
            // ignore
        }
    }

    get hasSelection() {
        return Boolean(this.state.inEvaluation && this.state.tonoContext && this.state.selectedPartidas.length);
    }

    get isAcabado() {
        return this.selectedMode === "acabado";
    }

    get selectedMode() {
        return this.state.selectedMode || this.state.tonoContext?.mode || "";
    }

    get selectedLineIds() {
        const ids = [];
        for (const partida of this.state.selectedPartidas || []) {
            for (const lineId of partida.line_ids || []) {
                const value = Number(lineId);
                if (value && !ids.includes(value)) {
                    ids.push(value);
                }
            }
        }
        return ids;
    }

    get availableModes() {
        return this.state.tonoContext?.available_modes || [];
    }

    get selectedModeLabel() {
        const mode = this.selectedMode;
        if (mode === "tacho") return "Tacho";
        if (mode === "secado") return "Secado";
        if (mode === "acabado") return "Acabado";
        return "No disponible";
    }

    get hasMotivosSelected() {
        return Boolean(this.state.motivo_tono || this.state.motivo_tacto || this.state.motivo_apariencia);
    }

    get canShowAprobar() {
        return !this.isAcabado || !this.hasMotivosSelected;
    }

    get canShowConcesionado() {
        return !this.isAcabado || this.hasMotivosSelected;
    }

    get canSubmitDecision() {
        if (this.selectedMode === "secado") {
            return true;
        }
        if (this.selectedMode === "tacho") {
            const receta = (this.state.receta || "").trim();
            const recetaTono = this.effectiveRecetaTono;
            return Boolean(receta && recetaTono);
        }
        return Boolean((this.state.receta || "").trim() && (this.state.receta_tono || "").trim());
    }

    get isTacho() {
        return this.selectedMode === "tacho";
    }

    get isSameRecetaTacho() {
        return this.isTacho && this.state.recetaTachoMode === "same";
    }

    get effectiveRecetaTono() {
        if (this.isSameRecetaTacho) {
            return (this.state.receta || "").trim();
        }
        return (this.state.receta_tono || "").trim();
    }

    get filteredPartidas() {
        const q = normalizeText(this.state.partidaQuery);
        const selectedIds = new Set((this.state.selectedPartidaIds || []).map((id) => `${id}`));
        const source = (this.state.partidas || []).filter((partida) => !selectedIds.has(`${partida.id}`));
        if (!q) return source.slice(0, 20);
        const results = source.filter((partida) => {
            return (
                normalizeText(partida.batch).includes(q) ||
                normalizeText(partida.customer).includes(q) ||
                normalizeText(partida.article).includes(q) ||
                normalizeText(partida.color_name).includes(q) ||
                normalizeText(partida.color_code).includes(q)
            );
        });
        return results.slice(0, 20);
    }

    async loadPartidas() {
        this.state.loading = true;
        this.state.error = "";
        try {
            const partidas = await this.orm.call("mrp.workorder.batch", "action_tablet_get_partidas_tono", ["", 50]);
            this.state.partidas = partidas || [];
            this._syncSelectedPartidas();
        } catch (error) {
            this.state.error = error.message || "No se pudo cargar la lista de partidas.";
        } finally {
            this.state.loading = false;
        }
    }

    _syncSelectedPartidas() {
        const selectedIds = (this.state.selectedPartidaIds || []).map((id) => `${id}`);
        if (!selectedIds.length) {
            this.state.selectedPartidas = [];
            return;
        }

        const currentById = new Map((this.state.selectedPartidas || []).map((p) => [`${p.id}`, p]));
        const sourceById = new Map((this.state.partidas || []).map((p) => [`${p.id}`, p]));
        const merged = [];

        for (const id of selectedIds) {
            const partida = sourceById.get(id) || currentById.get(id);
            if (partida) {
                merged.push(partida);
            }
        }

        this.state.selectedPartidas = merged;
        this.state.selectedPartidaIds = merged.map((p) => `${p.id}`);
    }

    onPartidaQueryInput(event) {
        const value = event.target.value || "";
        this.state.partidaQuery = value;

        this.state.showPartidaDropdown = Boolean(value);
        this._saveDraft();
        this._debouncedPartidaSearch(value);
    }

    onPartidaInputFocus() {
        if (this.state.partidaQuery) {
            this.state.showPartidaDropdown = true;
            this._saveDraft();
        }
    }

    clearSearchInput() {
        this.state.partidaQuery = "";
        this.state.showPartidaDropdown = false;
        this._saveDraft();
    }

    _debouncedPartidaSearch(query) {
        if (this._searchTimer) {
            clearTimeout(this._searchTimer);
        }
        this._searchTimer = setTimeout(() => this.searchPartidas(query), 250);
    }

    async searchPartidas(query) {
        this.state.isSearchingPartida = true;
        this.state.error = "";
        try {
            const q = (query || "").trim();
            const partidas = await this.orm.call("mrp.workorder.batch", "action_tablet_get_partidas_tono", [q, 50]);
            this.state.partidas = partidas || [];
            this._syncSelectedPartidas();
            this._saveDraft();
        } catch (error) {
            this.state.error = error.message || "No se pudo buscar partidas.";
        } finally {
            this.state.isSearchingPartida = false;
        }
    }

    async selectPartida(partidaId) {
        const partida = (this.state.partidas || []).find((p) => `${p.id}` === `${partidaId}`);
        if (!partida) {
            return;
        }
        if (!this.state.selectedPartidaIds.includes(`${partida.id}`)) {
            this.state.selectedPartidaIds = [...this.state.selectedPartidaIds, `${partida.id}`];
            this.state.selectedPartidas = [...this.state.selectedPartidas, partida];
        }
        // Cerrar dropdown para mostrar tags y el boton "Evaluar seleccionadas".
        // El usuario puede volver a escribir para agregar mas partidas.
        this.state.showPartidaDropdown = false;
        this.state.partidaQuery = "";
        this._saveDraft();
    }

    async removePartida(partidaId) {
        this.state.selectedPartidaIds = this.state.selectedPartidaIds.filter((id) => `${id}` !== `${partidaId}`);
        this._syncSelectedPartidas();
        if (!this.state.selectedPartidaIds.length) {
            this.clearSelection();
            this.state.showPartidaDropdown = false;
            this._clearDraft();
            return;
        }
        if (this.state.inEvaluation) {
            await this.loadTonoContext();
        }
        this._saveDraft();
    }

    clearSelection() {
        this.state.selectedPartidaIds = [];
        this.state.selectedPartidas = [];
        this.state.inEvaluation = false;
        this.state.tonoContext = null;
        this.state.selectedMode = "";
        this.state.receta = "";
        this.state.receta_tono = "";
        this.state.recetaTachoMode = "same";
        this.state.motivo_tono = false;
        this.state.motivo_tacto = false;
        this.state.motivo_apariencia = false;
        this._saveDraft();
    }

    clearSelectedPartida() {
        this.clearSelection();
        this.state.partidaQuery = "";
        this.state.showPartidaDropdown = false;
        this._clearDraft();
    }

    async loadTonoContext() {
        const pedidoLineIds = this.selectedLineIds;
        if (!pedidoLineIds.length) {
            this.state.tonoContext = null;
            return;
        }

        this.state.submitting = true;
        this.state.error = "";
        try {
            const context = await this.orm.call("mrp.workorder.batch", "action_tablet_get_tono_context", [pedidoLineIds]);
            this.state.tonoContext = context || null;
            this.state.selectedMode = context?.mode || "";
            this.state.receta = context?.receta || "";
            this.state.receta_tono = context?.receta_tono || "";
            this.state.recetaTachoMode = "same";
            this.state.motivo_tono = false;
            this.state.motivo_tacto = false;
            this.state.motivo_apariencia = false;
            this._syncSelectedPartidas();
            this._saveDraft();
        } catch (error) {
            this.state.error = error.message || "No se pudo cargar el contexto de evaluación de tono.";
            this.state.tonoContext = null;
        } finally {
            this.state.submitting = false;
        }
    }

    async startEvaluation() {
        if (!this.state.selectedPartidaIds.length || this.state.submitting) {
            return;
        }
        this.state.inEvaluation = true;
        this.state.showPartidaDropdown = false;
        await this.loadTonoContext();
    }

    onChangeReceta(event) {
        this.state.receta = event.target.value || "";
        if (this.isSameRecetaTacho) {
            this.state.receta_tono = this.state.receta;
        }
    }

    onChangeRecetaTono(event) {
        this.state.receta_tono = event.target.value || "";
    }

    onChangeRecetaTachoMode(event) {
        const value = (event.target.value || "same").trim();
        this.state.recetaTachoMode = value === "different" ? "different" : "same";
        if (this.state.recetaTachoMode === "same") {
            this.state.receta_tono = this.state.receta || "";
        } else {
            this.state.receta_tono = "";
        }
    }

    onToggleMotivo(fieldName, event) {
        this.state[fieldName] = Boolean(event.target.checked);
    }

    onSelectMode(mode) {
        if (!this.availableModes.includes(mode)) {
            return;
        }
        this.state.selectedMode = mode;
        this.state.recetaTachoMode = "same";
        if (mode !== "acabado") {
            this.state.motivo_tono = false;
            this.state.motivo_tacto = false;
            this.state.motivo_apariencia = false;
        }
        if (mode === "tacho") {
            this.state.receta_tono = this.state.receta || "";
        } else if (this.state.tonoContext?.receta_tono) {
            this.state.receta_tono = this.state.tonoContext.receta_tono;
        }
    }

    async submitDecision(decision) {
        if (!this.state.tonoContext?.can_evaluate || this.state.submitting) {
            return;
        }
        if (!this.canSubmitDecision) {
            this.notification.add("Debes completar las recetas.", { type: "warning" });
            return;
        }

        this.state.submitting = true;
        this.state.error = "";
        try {
            await this.orm.call("mrp.workorder.batch", "action_tablet_submit_tono", [
                this.selectedLineIds,
                decision,
                this.state.receta,
                this.effectiveRecetaTono,
                this.state.motivo_tono,
                this.state.motivo_tacto,
                this.state.motivo_apariencia,
                this.selectedMode,
            ]);

            this.notification.add("Evaluación registrada.", { type: "success" });
            await this.loadPartidas();
            // Regresar a pantalla de seleccion despues de registrar una decision.
            this.clearSelection();
            this.state.partidaQuery = "";
            this.state.showPartidaDropdown = false;
            this._clearDraft();
        } catch (error) {
            this.state.error = error.message || "No se pudo registrar la evaluación de tono.";
        } finally {
            this.state.submitting = false;
        }
    }

    async close() {
        this._saveDraft();
        if (window.history.length > 1) {
            window.history.back();
            return;
        }
        await this.homeMenu.toggle();
    }

    onClickRefresh() {
        window.location.reload();
    }

    onBackToSearch() {
        this.state.inEvaluation = false;
        this.state.tonoContext = null;
        this.state.showPartidaDropdown = false;
        this._saveDraft();
    }
}

QualityToneScreen.template = "idtx_quality_control.QualityToneScreen";
registry.category("actions").add("idtx_quality_control.tone_screen", QualityToneScreen);
