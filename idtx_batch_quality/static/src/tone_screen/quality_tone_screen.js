/** @odoo-module */

import { Component, onWillStart, onMounted, onWillUnmount, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

const DRAFT_STORAGE_KEY = "idtx_batch_quality.tone_screen.draft.v1";

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

            selectedPartidaId: "",
            selectedPartidaData: null,

            tonoContext: null,
            receta: "",
            receta_tono: "",
            motivo_tono: false,
            motivo_tacto: false,
            motivo_apariencia: false,
        });

        onWillStart(async () => {
            this._restoreDraft();
            await this.loadPartidas();
            this._syncSelectedPartidaData();
            if (this.state.selectedPartidaId) {
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
            selectedPartidaId: this.state.selectedPartidaId ? String(this.state.selectedPartidaId) : "",
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
        this.state.selectedPartidaId = draft.selectedPartidaId ? String(draft.selectedPartidaId) : "";
        this.state.showPartidaDropdown =
            Boolean(draft.showPartidaDropdown) && !this.state.selectedPartidaId;
    }

    _clearDraft() {
        try {
            window.localStorage.removeItem(DRAFT_STORAGE_KEY);
        } catch {
            // ignore
        }
    }

    get hasSelection() {
        return Boolean(this.state.tonoContext && this.state.selectedPartidaId);
    }

    get isAcabado() {
        return this.state.tonoContext?.mode === "acabado";
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
        return Boolean((this.state.receta || "").trim() && (this.state.receta_tono || "").trim());
    }

    get filteredPartidas() {
        const q = normalizeText(this.state.partidaQuery);
        if (!q) return (this.state.partidas || []).slice(0, 20);
        const results = (this.state.partidas || []).filter((partida) => {
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
            const partidas = await this.orm.call("control.pedido.line", "action_tablet_get_partidas_tono", ["", 50]);
            this.state.partidas = partidas || [];
            this._syncSelectedPartidaData();
        } catch (error) {
            this.state.error = error.message || "No se pudo cargar la lista de partidas.";
        } finally {
            this.state.loading = false;
        }
    }

    _syncSelectedPartidaData() {
        if (!this.state.selectedPartidaId) {
            this.state.selectedPartidaData = null;
            return;
        }
        const found = (this.state.partidas || []).find((p) => `${p.id}` === `${this.state.selectedPartidaId}`);
        this.state.selectedPartidaData = found || this.state.selectedPartidaData || null;
        if (this.state.selectedPartidaData?.batch) {
            this.state.partidaQuery = String(this.state.selectedPartidaData.batch);
        }
    }

    onPartidaQueryInput(event) {
        const value = event.target.value || "";
        this.state.partidaQuery = value;

        if (this.state.selectedPartidaId) {
            const currentBatch = this.state.selectedPartidaData?.batch ? String(this.state.selectedPartidaData.batch) : "";
            if (value !== currentBatch) {
                this.clearSelection();
                this.state.partidaQuery = value;
            }
        }

        this.state.showPartidaDropdown = Boolean(value) && !this.state.selectedPartidaId;
        this._saveDraft();
        this._debouncedPartidaSearch(value);
    }

    onPartidaInputFocus() {
        if (!this.state.selectedPartidaId && this.state.partidaQuery) {
            this.state.showPartidaDropdown = true;
            this._saveDraft();
        }
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
            const partidas = await this.orm.call("control.pedido.line", "action_tablet_get_partidas_tono", [q, 50]);
            this.state.partidas = partidas || [];
            this._syncSelectedPartidaData();
            this._saveDraft();
        } catch (error) {
            this.state.error = error.message || "No se pudo buscar partidas.";
        } finally {
            this.state.isSearchingPartida = false;
        }
    }

    async selectPartida(partidaId) {
        this.state.selectedPartidaId = String(partidaId);
        this._syncSelectedPartidaData();
        this.state.showPartidaDropdown = false;
        this._saveDraft();
        await this.loadTonoContext();
    }

    clearSelection() {
        this.state.selectedPartidaId = "";
        this.state.selectedPartidaData = null;
        this.state.tonoContext = null;
        this.state.receta = "";
        this.state.receta_tono = "";
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
        const pedidoLineId = Number(this.state.selectedPartidaId || 0);
        if (!pedidoLineId) {
            this.state.tonoContext = null;
            return;
        }

        this.state.submitting = true;
        this.state.error = "";
        try {
            const context = await this.orm.call("control.pedido.line", "action_tablet_get_tono_context", [pedidoLineId]);
            this.state.tonoContext = context || null;
            this.state.receta = context?.receta || "";
            this.state.receta_tono = context?.receta_tono || "";
            this.state.motivo_tono = false;
            this.state.motivo_tacto = false;
            this.state.motivo_apariencia = false;
            this._syncSelectedPartidaData();
            this._saveDraft();
        } catch (error) {
            this.state.error = error.message || "No se pudo cargar el contexto de evaluación de tono.";
            this.state.tonoContext = null;
        } finally {
            this.state.submitting = false;
        }
    }

    onChangeReceta(event) {
        this.state.receta = event.target.value || "";
    }

    onChangeRecetaTono(event) {
        this.state.receta_tono = event.target.value || "";
    }

    onToggleMotivo(fieldName, event) {
        this.state[fieldName] = Boolean(event.target.checked);
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
            await this.orm.call("control.pedido.line", "action_tablet_submit_tono", [
                Number(this.state.selectedPartidaId),
                decision,
                this.state.receta,
                this.state.receta_tono,
                this.state.motivo_tono,
                this.state.motivo_tacto,
                this.state.motivo_apariencia,
            ]);

            this.notification.add("Evaluación registrada.", { type: "success" });
            await this.loadPartidas();
            await this.loadTonoContext();
            this._saveDraft();
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
        this.clearSelection();
        this.state.showPartidaDropdown = false;
        this._saveDraft();
    }
}

QualityToneScreen.template = "idtx_batch_quality.QualityToneScreen";
registry.category("actions").add("idtx_quality.tone_screen", QualityToneScreen);
