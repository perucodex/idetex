/** @odoo-module */

import { Component, onWillStart, onMounted, onWillUnmount, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

const PRINT_SIZE_OPTIONS = [
    { value: "1", label: "Hasta 7.62 cm" },
    { value: "2", label: "> 7.62 cm y hasta 15.24 cm" },
    { value: "3", label: "> 15.24 cm y hasta 22.86 cm" },
    { value: "4", label: "> 22.86 cm" },
];

const DRAFT_STORAGE_KEY = "idtx_batch_printing.defect_screen.draft.v2";

function safeJsonParse(value) {
    try {
        return JSON.parse(value);
    } catch {
        return null;
    }
}

function normalizeText(v) {
    return (v || "").toString().toLowerCase().trim();
}

function parsePositiveFloat(value) {
    const normalized = (value || "").toString().replace(",", ".").trim();
    const parsed = Number(normalized);
    return Number.isFinite(parsed) ? parsed : 0;
}

export class QualityDefectScreen extends Component {
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
        this._rolloValidateTimer = null;
        this._rolloValidateSeq = 0;

        this.state = useState({
            loading: true,
            submitting: false,
            error: "",

            // Partidas (autocomplete)
            partidas: [],
            partidaQuery: "",
            isSearchingPartida: false,
            showPartidaDropdown: false,

            // Selected basics
            selectedPartidaId: "",
            selectedPartidaData: null,
            rolloNum: "",
            width: "",
            meters: "",
            rolloValidationError: "",
            isCheckingRollo: false,

            // Session
            sessionActive: false,
            defects: [],
            selectedDefectoId: false,
            sizePopupOpen: false,
            popupDefectId: false,
            meterPopupOpen: false,
        });

        onWillStart(async () => {
            this._restoreDraft();
            await this.loadPartidas();

            if (this.state.sessionActive) {
                await this._restoreSessionDefectsFromServer();
            }
            this._syncSelectedPartidaData();
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

    get hasSession() {
        return Boolean(this.state.sessionActive);
    }

    get canProceedBasics() {
        return (
            Boolean(this.state.selectedPartidaId) &&
            Number(this.state.rolloNum) > 0 &&
            parsePositiveFloat(this.state.width) > 0 &&
            !this.state.submitting &&
            !this.state.isCheckingRollo &&
            !this.state.rolloValidationError
        );
    }

    get isFinalizeDisabled() {
        return !this.hasSession || this.state.submitting;
    }

    get popupDefect() {
        return this.state.defects.find((defect) => defect.defecto_id === this.state.popupDefectId);
    }

    get sizeOptions() {
        return PRINT_SIZE_OPTIONS;
    }

    get selectedDefects() {
        return (this.state.defects || []).filter((d) => (d.sizes || []).length);
    }

    get shouldShowRolloInput() {
        return Boolean(this.state.selectedPartidaId) && !this.hasSession;
    }

    get filteredPartidas() {
        const q = normalizeText(this.state.partidaQuery);
        if (!q) return (this.state.partidas || []).slice(0, 20);
        const res = (this.state.partidas || []).filter((p) => {
            return (
                normalizeText(p.batch).includes(q) ||
                normalizeText(p.customer).includes(q) ||
                normalizeText(p.article).includes(q) ||
                normalizeText(p.color_name).includes(q) ||
                normalizeText(p.color_code).includes(q)
            );
        });
        return res.slice(0, 20);
    }

    getSizeBreakdown(defect) {
        const counts = {};
        for (const size of defect.sizes || []) {
            const key = String(size);
            counts[key] = (counts[key] || 0) + 1;
        }
        return PRINT_SIZE_OPTIONS
            .filter((opt) => counts[opt.value])
            .map((opt) => ({ value: opt.value, label: opt.label, qty: counts[opt.value] }));
    }

    _saveDraft() {
        const draft = {
            partidaQuery: this.state.partidaQuery || "",
            showPartidaDropdown: Boolean(this.state.showPartidaDropdown),
            selectedPartidaId: this.state.selectedPartidaId ? String(this.state.selectedPartidaId) : "",
            rolloNum: this.state.rolloNum ? String(this.state.rolloNum) : "",
            width: this.state.width ? String(this.state.width) : "",
            meters: this.state.meters ? String(this.state.meters) : "",
            sessionActive: Boolean(this.state.sessionActive),
            defectsSizes: {},
        };

        if (draft.sessionActive) {
            for (const d of this.state.defects || []) {
                if ((d.sizes || []).length) {
                    draft.defectsSizes[String(d.defecto_id)] = [...d.sizes];
                }
            }
        }

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
        this.state.rolloNum = draft.rolloNum ? String(draft.rolloNum) : "";
        this.state.width = draft.width ? String(draft.width) : "";
        this.state.meters = draft.meters ? String(draft.meters) : "";

        const hasBasics =
            Boolean(this.state.selectedPartidaId) &&
            Number(this.state.rolloNum) > 0 &&
            parsePositiveFloat(this.state.width) > 0;
        this.state.sessionActive = Boolean(draft.sessionActive) && hasBasics;

        this.state.showPartidaDropdown =
            Boolean(draft.showPartidaDropdown) && !this.state.selectedPartidaId && !this.state.sessionActive;

        this._draftDefectsSizes =
            draft.defectsSizes && typeof draft.defectsSizes === "object" ? draft.defectsSizes : {};
    }

    _clearDraft() {
        try {
            window.localStorage.removeItem(DRAFT_STORAGE_KEY);
        } catch {
            // ignore
        }
        this._draftDefectsSizes = {};
    }

    _syncSelectedPartidaData() {
        if (!this.state.selectedPartidaId) {
            this.state.selectedPartidaData = null;
            return;
        }
        const found = (this.state.partidas || []).find((p) => `${p.id}` === `${this.state.selectedPartidaId}`);
        this.state.selectedPartidaData = found || this.state.selectedPartidaData || null;

        if (this.state.selectedPartidaData?.batch && !this.state.sessionActive) {
            this.state.partidaQuery = String(this.state.selectedPartidaData.batch);
        }
    }

    async _restoreSessionDefectsFromServer() {
        try {
            const defects = await this.orm.call(
                "control.apariencia.line",
                "action_tablet_get_defectos_printing",
                [Number(this.state.selectedPartidaId || 0)]
            );
            const sizesMap = this._draftDefectsSizes || {};
            this.state.defects = (defects || []).map((defect) => {
                const savedSizes = sizesMap[String(defect.defecto_id)] || [];
                return {
                    ...defect,
                    sizes: Array.isArray(savedSizes) ? [...savedSizes] : [],
                    count: Array.isArray(savedSizes) ? savedSizes.length : 0,
                };
            });
        } catch (error) {
            this.state.sessionActive = false;
            this.state.defects = [];
            this.state.error = error.message || "No se pudo restaurar la sesión. Inicie nuevamente.";
        }
    }

    async loadPartidas() {
        this.state.loading = true;
        this.state.error = "";
        try {
            const partidas = await this.orm.call("control.apariencia.line", "action_tablet_get_partidas", ["", 50]);
            this.state.partidas = partidas || [];
            this._syncSelectedPartidaData();
        } catch (error) {
            this.state.error = error.message || "No se pudo cargar la lista de partidas.";
        } finally {
            this.state.loading = false;
        }
    }

    onPartidaQueryInput(event) {
        const value = event.target.value || "";
        this.state.partidaQuery = value;

        if (this.state.selectedPartidaId) {
            const currentBatch = this.state.selectedPartidaData?.batch ? String(this.state.selectedPartidaData.batch) : "";
            if (value !== currentBatch) {
                this.state.selectedPartidaId = "";
                this.state.selectedPartidaData = null;
                this.state.rolloNum = "";
                this.state.width = "";
                this.state.meters = "";
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
        this._searchTimer = setTimeout(() => {
            this.searchPartidas(query);
        }, 250);
    }

    async searchPartidas(query) {
        this.state.isSearchingPartida = true;
        this.state.error = "";
        try {
            const q = (query || "").trim();
            const partidas = await this.orm.call("control.apariencia.line", "action_tablet_get_partidas", [q, 50]);
            this.state.partidas = partidas || [];
            this._syncSelectedPartidaData();
            this._saveDraft();
        } catch (error) {
            this.state.error = error.message || "No se pudo buscar partidas.";
        } finally {
            this.state.isSearchingPartida = false;
        }
    }

    selectPartida(partidaId) {
        this.state.selectedPartidaId = String(partidaId);
        this._syncSelectedPartidaData();
        this.state.showPartidaDropdown = false;
        this._saveDraft();
        if (Number(this.state.rolloNum) > 0) {
            this._debouncedValidateRollo();
        }
    }

    isPartidaSelected(partidaId) {
        return `${partidaId}` === `${this.state.selectedPartidaId}`;
    }

    clearSelectedPartida() {
        this.state.selectedPartidaId = "";
        this.state.selectedPartidaData = null;
        this.state.rolloNum = "";
        this.state.width = "";
        this.state.meters = "";
        this.state.rolloValidationError = "";
        this.state.isCheckingRollo = false;
        this.state.partidaQuery = "";
        this.state.showPartidaDropdown = false;
        this._saveDraft();
    }

    onChangeRollo(event) {
        this.state.rolloNum = event.target.value;
        this._debouncedValidateRollo();
        this._saveDraft();
    }

    onChangeWidth(event) {
        this.state.width = event.target.value;
        this._saveDraft();
    }

    onChangeMeters(event) {
        this.state.meters = event.target.value;
        this._saveDraft();
    }

    _debouncedValidateRollo() {
        if (this._rolloValidateTimer) {
            clearTimeout(this._rolloValidateTimer);
        }
        this._rolloValidateTimer = setTimeout(() => {
            this._validateRolloUnique();
        }, 250);
    }

    async _validateRolloUnique() {
        const pedidoLineId = Number(this.state.selectedPartidaId || 0);
        const rolloNum = Number(this.state.rolloNum || 0);

        if (!pedidoLineId || rolloNum <= 0) {
            this.state.rolloValidationError = "";
            this.state.isCheckingRollo = false;
            return true;
        }

        const seq = ++this._rolloValidateSeq;
        this.state.isCheckingRollo = true;
        try {
            const result = await this.orm.call(
                "control.apariencia.line",
                "action_tablet_check_rollo_available_printing",
                [pedidoLineId, rolloNum]
            );
            if (seq !== this._rolloValidateSeq) {
                return false;
            }
            this.state.rolloValidationError = result?.ok ? "" : (result?.message || "Rollo no disponible.");
            return Boolean(result?.ok);
        } catch (error) {
            if (seq === this._rolloValidateSeq) {
                this.state.rolloValidationError = error.message || "No se pudo validar el número de rollo.";
            }
            return false;
        } finally {
            if (seq === this._rolloValidateSeq) {
                this.state.isCheckingRollo = false;
            }
        }
    }

    async onNext() {
        if (!this.canProceedBasics) return;

        const isRolloValid = await this._validateRolloUnique();
        if (!isRolloValid) {
            return;
        }
        this.state.submitting = true;
        this.state.error = "";
        try {
            const defects = await this.orm.call(
                "control.apariencia.line",
                "action_tablet_get_defectos_printing",
                [Number(this.state.selectedPartidaId || 0)]
            );
            this.state.defects = (defects || []).map((defect) => ({ ...defect, sizes: [], count: 0 }));

            this._syncSelectedPartidaData();
            this.state.sessionActive = true;
            this.state.showPartidaDropdown = false;

            this._saveDraft();
            this.notification.add("Listo. Ahora registre los defectos.", { type: "success" });
        } catch (error) {
            this.state.error = error.message || "No se pudo continuar.";
        } finally {
            this.state.submitting = false;
        }
    }

    onSelectDefect(defectoId) {
        if (!this.hasSession) return;
        this.state.selectedDefectoId = defectoId;
        this.state.popupDefectId = defectoId;
        this.state.sizePopupOpen = true;
        this._saveDraft();
    }

    onSelectSize(sizeCode) {
        if (!this.hasSession || !this.popupDefect) return;

        const defect = this.state.defects.find((item) => item.defecto_id === this.state.popupDefectId);
        if (!defect) {
            return;
        }
        if (!this.sizeOptions.some((opt) => opt.value === String(sizeCode))) {
            this.notification.add("Invalid size for this defect.", { type: "danger" });
            return;
        }

        defect.sizes.push(String(sizeCode));
        defect.count = defect.sizes.length;
        this._saveDraft();
        this.closeSizePopup();
    }

    closeSizePopup() {
        this.state.sizePopupOpen = false;
        this.state.popupDefectId = false;
        this._saveDraft();
    }

    removeLastOccurrence(defectoId) {
        const defect = this.state.defects.find((d) => d.defecto_id === defectoId);
        if (!defect || !(defect.sizes || []).length) {
            return;
        }
        defect.sizes.pop();
        defect.count = defect.sizes.length;
        this._saveDraft();
    }

    clearDefect(defectoId) {
        const defect = this.state.defects.find((d) => d.defecto_id === defectoId);
        if (!defect) {
            return;
        }
        defect.sizes = [];
        defect.count = 0;
        if (this.state.selectedDefectoId === defectoId) {
            this.state.selectedDefectoId = false;
        }
        this._saveDraft();
    }

    clearAllSelections() {
        for (const defect of this.state.defects || []) {
            defect.sizes = [];
            defect.count = 0;
        }
        this.state.selectedDefectoId = false;
        this._saveDraft();
    }

    async onFinalize() {
        if (this.isFinalizeDisabled) {
            return;
        }

        this.state.meterPopupOpen = true;
        this._saveDraft();
    }

    closeMeterPopup() {
        this.state.meterPopupOpen = false;
        this._saveDraft();
    }

    async confirmFinalize() {
        if (this.isFinalizeDisabled) {
            return;
        }

        const metersValue = parsePositiveFloat(this.state.meters);
        if (metersValue <= 0) {
            this.notification.add("El metraje debe ser mayor a 0.", { type: "warning" });
            return;
        }

        this.state.submitting = true;
        this.state.error = "";
        try {
            const selections = this.state.defects
                .filter((defect) => (defect.count || 0) > 0)
                .map((defect) => ({
                    defecto_id: defect.defecto_id,
                    count: defect.count,
                    sizes: defect.sizes || [],
                }));

            await this.orm.call("control.apariencia.line", "action_tablet_finalize_printing", [
                Number(this.state.selectedPartidaId),
                Number(this.state.rolloNum),
                selections,
                parsePositiveFloat(this.state.width),
                metersValue,
            ]);
            this.notification.add("Registro guardado.", { type: "success" });
            this.state.meterPopupOpen = false;
            this.prepareNextRoll();
            await this.loadPartidas();
        } catch (error) {
            this.state.error = error.message || "No se pudo finalizar el registro.";
        } finally {
            this.state.submitting = false;
        }
    }

    prepareNextRoll() {
        const selectedPartidaId = this.state.selectedPartidaId;
        const selectedPartidaData = this.state.selectedPartidaData;
        const partidaQuery = selectedPartidaData?.batch ? String(selectedPartidaData.batch) : this.state.partidaQuery;

        this.state.partidaQuery = partidaQuery || "";
        this.state.selectedPartidaId = selectedPartidaId || "";
        this.state.selectedPartidaData = selectedPartidaData || null;
        this.state.rolloNum = "";
        this.state.width = "";
        this.state.meters = "";
        this.state.rolloValidationError = "";
        this.state.isCheckingRollo = false;
        this.state.showPartidaDropdown = false;

        this.state.sessionActive = false;
        this.state.defects = [];
        this.state.selectedDefectoId = false;
        this.state.sizePopupOpen = false;
        this.state.popupDefectId = false;
        this.state.meterPopupOpen = false;

        this._saveDraft();
    }

    resetScreen() {
        this.state.partidaQuery = "";
        this.state.selectedPartidaId = "";
        this.state.selectedPartidaData = null;
        this.state.rolloNum = "";
        this.state.width = "";
        this.state.meters = "";
        this.state.rolloValidationError = "";
        this.state.isCheckingRollo = false;
        this.state.showPartidaDropdown = false;

        this.state.sessionActive = false;
        this.state.defects = [];
        this.state.selectedDefectoId = false;
        this.state.sizePopupOpen = false;
        this.state.popupDefectId = false;
        this.state.meterPopupOpen = false;

        this._clearDraft();
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
        this._saveDraft();
        window.location.reload();
    }

    onClearDraftClick() {
        this.resetScreen();
        this.notification.add("Borrador limpiado.", { type: "info" });
    }

    onBackToBasics() {
        this.state.sessionActive = false;
        this.state.defects = [];
        this.state.selectedDefectoId = false;
        this.state.sizePopupOpen = false;
        this.state.popupDefectId = false;
        this._saveDraft();
    }
}

QualityDefectScreen.template = "idtx_batch_printing.QualityDefectScreen";

registry.category("actions").add("idtx_quality.defect_screen_printing", QualityDefectScreen);
