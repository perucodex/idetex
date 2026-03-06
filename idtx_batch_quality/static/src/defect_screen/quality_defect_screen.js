/** @odoo-module */

import { Component, onWillStart, onMounted, onWillUnmount, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

const DEFECT_SIZE_OPTIONS = [
    { value: "1", label: "Hasta 7.5 cm" },
    { value: "2", label: "> 7.5 cm y hasta 15 cm" },
    { value: "3", label: "> 15 cm y hasta 23 cm" },
    { value: "4", label: "> 23 cm" },
];

const HUECO_SIZE_OPTIONS = [
    { value: "2", label: "<= 3 cm" },
    { value: "4", label: "> 3 cm" },
];

const DRAFT_STORAGE_KEY = "idtx_batch_quality.defect_screen.draft.v3";

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

            // Apariencias (autocomplete)
            apariencias: [],
            aparienciaQuery: "",
            selectedAparienciaId: "",
            selectedAparienciaData: null,
            isSearchingApariencia: false,
            showAparienciaDropdown: false,

            // Partidas (autocomplete)
            partidas: [],
            partidaQuery: "",
            isSearchingPartida: false,
            showPartidaDropdown: false,

            // Selected basics
            selectedPartidaId: "",
            selectedPartidaData: null,
            selectedEvaluacionId: "",
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
            await this.loadApariencias();
            await this.loadPartidas();

            if (this.state.sessionActive) {
                await this._restoreSessionDefectsFromServer();
            }
            this._syncSelectedPartidaData();
        });

        onMounted(() => {
            this._beforeUnloadHandler = () => this._saveDraft();
            window.addEventListener("beforeunload", this._beforeUnloadHandler);

            // Click-outside closes dropdown (mobile friendly)
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

    // ---------- Computed ----------
    get hasSession() {
        return Boolean(this.state.sessionActive);
    }

    get canProceedBasics() {
        return (
            Boolean(this.state.selectedAparienciaId) &&
            Boolean(this.state.selectedPartidaId) &&
            Number(this.state.rolloNum) > 0 &&
            parsePositiveFloat(this.state.width) > 0 &&
            !this.state.submitting &&
            !this.state.isCheckingRollo &&
            !this.state.rolloValidationError
        );
    }

    get popupDefect() {
        return this.state.defects.find((defect) => defect.defecto_id === this.state.popupDefectId);
    }

    get sizeOptions() {
        if (!this.popupDefect) return [];
        return this.popupDefect.is_hueco ? HUECO_SIZE_OPTIONS : DEFECT_SIZE_OPTIONS;
    }

    get isFinalizeDisabled() {
        return !this.hasSession || this.state.submitting;
    }

    get selectedDefects() {
        return (this.state.defects || []).filter((d) => (d.sizes || []).length);
    }

    // Rollo aparece SOLO cuando ya se seleccionó una partida (y aún no empezó captura)
    get shouldShowRolloInput() {
        return Boolean(this.state.selectedAparienciaId) && Boolean(this.state.selectedPartidaId) && !this.hasSession;
    }

    get filteredApariencias() {
        const q = normalizeText(this.state.aparienciaQuery);
        if (!q) return (this.state.apariencias || []).slice(0, 20);
        return (this.state.apariencias || [])
            .filter((a) => normalizeText(a.name).includes(q))
            .slice(0, 20);
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

    // ---------- Draft persistence ----------
    _saveDraft() {
        const draft = {
            aparienciaQuery: this.state.aparienciaQuery || "",
            selectedAparienciaId: this.state.selectedAparienciaId ? String(this.state.selectedAparienciaId) : "",
            partidaQuery: this.state.partidaQuery || "",
            showAparienciaDropdown: Boolean(this.state.showAparienciaDropdown),
            showPartidaDropdown: Boolean(this.state.showPartidaDropdown),
            selectedPartidaId: this.state.selectedPartidaId ? String(this.state.selectedPartidaId) : "",
            selectedEvaluacionId: this.state.selectedEvaluacionId ? String(this.state.selectedEvaluacionId) : "",
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

        this.state.aparienciaQuery = typeof draft.aparienciaQuery === "string" ? draft.aparienciaQuery : "";
        this.state.selectedAparienciaId = draft.selectedAparienciaId ? String(draft.selectedAparienciaId) : "";
        this.state.partidaQuery = typeof draft.partidaQuery === "string" ? draft.partidaQuery : "";
        this.state.selectedPartidaId = draft.selectedPartidaId ? String(draft.selectedPartidaId) : "";
        this.state.selectedEvaluacionId = draft.selectedEvaluacionId ? String(draft.selectedEvaluacionId) : "";
        this.state.rolloNum = draft.rolloNum ? String(draft.rolloNum) : "";
        this.state.width = draft.width ? String(draft.width) : "";
        this.state.meters = draft.meters ? String(draft.meters) : "";

        const hasBasics =
            Boolean(this.state.selectedAparienciaId) &&
            Boolean(this.state.selectedPartidaId) &&
            Number(this.state.rolloNum) > 0 &&
            parsePositiveFloat(this.state.width) > 0;
        this.state.sessionActive = Boolean(draft.sessionActive) && hasBasics;

        this.state.showAparienciaDropdown =
            Boolean(draft.showAparienciaDropdown) && !this.state.selectedAparienciaId && !this.state.sessionActive;

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

    _syncSelectedAparienciaData() {
        if (!this.state.selectedAparienciaId) {
            this.state.selectedAparienciaData = null;
            return;
        }
        const found = (this.state.apariencias || []).find((a) => `${a.id}` === `${this.state.selectedAparienciaId}`);
        this.state.selectedAparienciaData = found || this.state.selectedAparienciaData || null;
        if (this.state.selectedAparienciaData?.name && !this.state.sessionActive) {
            this.state.aparienciaQuery = String(this.state.selectedAparienciaData.name);
        }
    }

    _syncSelectedPartidaData() {
        if (!this.state.selectedPartidaId) {
            this.state.selectedPartidaData = null;
            return;
        }
        const found = (this.state.partidas || []).find((p) => `${p.id}` === `${this.state.selectedPartidaId}`);
        this.state.selectedPartidaData = found || this.state.selectedPartidaData || null;

        // Al seleccionar partida, el input queda con el batch
        if (this.state.selectedPartidaData?.batch && !this.state.sessionActive) {
            this.state.partidaQuery = String(this.state.selectedPartidaData.batch);
        }
    }

    async _restoreSessionDefectsFromServer() {
        if (!this.state.selectedAparienciaId) {
            this.state.sessionActive = false;
            this.state.defects = [];
            return;
        }
        try {
            const defects = await this.orm.call(
                "control.apariencia.line",
                "action_tablet_get_defectos",
                [Number(this.state.selectedAparienciaId)],
                { context: { appearance_type: "quality" } }
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

    // ---------- Data loading ----------
    async loadApariencias() {
        this.state.loading = true;
        this.state.error = "";
        try {
            const apariencias = await this.orm.call("control.apariencia.line", "action_tablet_get_apariencias", ["", 50]);
            this.state.apariencias = apariencias || [];
            this._syncSelectedAparienciaData();
        } catch (error) {
            this.state.error = error.message || "No se pudo cargar la lista de apariencias.";
        } finally {
            this.state.loading = false;
        }
    }

    async loadPartidas() {
        this.state.loading = true;
        this.state.error = "";
        try {
            // Traemos varias y filtramos localmente SOLO por batch
            const partidas = await this.orm.call("control.apariencia.line", "action_tablet_get_partidas", ["", 50]);
            this.state.partidas = partidas || [];
            this._syncSelectedPartidaData();
        } catch (error) {
            this.state.error = error.message || "No se pudo cargar la lista de partidas.";
        } finally {
            this.state.loading = false;
        }
    }

    // ---------- Autocomplete Apariencia ----------
    onAparienciaSelectChange(event) {
        this.state.selectedAparienciaId = event.target.value || this.state.selectedAparienciaId || "";
        this._syncSelectedAparienciaData();
        this._saveDraft();
    }

    onAparienciaQueryInput(event) {
        const value = event.target.value || "";
        this.state.aparienciaQuery = value;

        if (this.state.selectedAparienciaId) {
            const currentName = this.state.selectedAparienciaData?.name ? String(this.state.selectedAparienciaData.name) : "";
            if (value !== currentName) {
                this.state.selectedAparienciaId = "";
                this.state.selectedAparienciaData = null;
            }
        }

        this.state.showAparienciaDropdown = Boolean(value) && !this.state.selectedAparienciaId;
        this._saveDraft();
        this._debouncedAparienciaSearch(value);
    }

    onAparienciaInputFocus() {
        if (!this.state.selectedAparienciaId && this.state.aparienciaQuery) {
            this.state.showAparienciaDropdown = true;
            this._saveDraft();
        }
    }

    _debouncedAparienciaSearch(query) {
        if (this._aparienciaSearchTimer) clearTimeout(this._aparienciaSearchTimer);
        this._aparienciaSearchTimer = setTimeout(() => this.searchApariencias(query), 250);
    }

    async searchApariencias(query) {
        this.state.isSearchingApariencia = true;
        this.state.error = "";
        try {
            const q = (query || "").trim();
            const apariencias = await this.orm.call("control.apariencia.line", "action_tablet_get_apariencias", [q, 50]);
            this.state.apariencias = apariencias || [];
            this._syncSelectedAparienciaData();
            this._saveDraft();
        } catch (error) {
            this.state.error = error.message || "No se pudo buscar apariencias.";
        } finally {
            this.state.isSearchingApariencia = false;
        }
    }

    selectApariencia(aparienciaId) {
        this.state.selectedAparienciaId = String(aparienciaId);
        this._syncSelectedAparienciaData();
        this.state.showAparienciaDropdown = false;
        this._saveDraft();
    }

    clearSelectedApariencia() {
        this.state.selectedAparienciaId = "";
        this.state.selectedAparienciaData = null;
        this.state.aparienciaQuery = "";
        this.state.showAparienciaDropdown = false;
        this._saveDraft();
    }

    // ---------- Autocomplete Partida ----------
    onPartidaQueryInput(event) {
        const value = event.target.value || "";
        this.state.partidaQuery = value;

        // Si estaba seleccionada y el usuario edita, limpiamos selección (comportamiento autocomplete)
        if (this.state.selectedPartidaId) {
            const currentBatch = this.state.selectedPartidaData?.batch ? String(this.state.selectedPartidaData.batch) : "";
            if (value !== currentBatch) {
                this.state.selectedPartidaId = "";
                this.state.selectedPartidaData = null;
                this.state.selectedEvaluacionId = "";
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
        if (this._searchTimer) clearTimeout(this._searchTimer);
        this._searchTimer = setTimeout(() => this.searchPartidas(query), 250);
    }

    async searchPartidas(query) {
        this.state.isSearchingPartida = true;
        this.state.error = "";
        try {
            // Llamada al server (rápida); UI filtra SOLO por batch
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
        this.state.selectedEvaluacionId = "";
        this.state.rolloNum = "";
        this.state.width = "";
        this.state.meters = "";
        this.state.rolloValidationError = "";
        this.state.isCheckingRollo = false;
        this.state.partidaQuery = "";
        this.state.showPartidaDropdown = false;
        this._saveDraft();
    }

    // ---------- Rollo ----------
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
                "action_tablet_check_rollo_available",
                [pedidoLineId, rolloNum, Number(this.state.selectedEvaluacionId || 0)],
                { context: { appearance_type: "quality" } }
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

    // ---------- Paso 1 -> Paso 2 ----------
    async onNext() {
        if (!this.state.selectedAparienciaId) {
            this.notification.add("Seleccione un control de apariencia.", { type: "warning" });
            return;
        }
        if (!this.canProceedBasics) return;

        const isRolloValid = await this._validateRolloUnique();
        if (!isRolloValid) {
            return;
        }

        this.state.submitting = true;
        this.state.error = "";
        try {
            const evaluacion = await this.orm.call(
                "control.apariencia.eval",
                "action_tablet_get_or_create_evaluacion",
                [
                    Number(this.state.selectedPartidaId),
                    Number(this.state.selectedAparienciaId),
                    Number(this.state.selectedEvaluacionId || 0),
                ],
                { context: { appearance_type: "quality" } }
            );
            this.state.selectedEvaluacionId = evaluacion?.id ? String(evaluacion.id) : "";

            const defects = await this.orm.call(
                "control.apariencia.line",
                "action_tablet_get_defectos",
                [Number(this.state.selectedAparienciaId)],
                { context: { appearance_type: "quality" } }
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

    // ---------- Captura de defectos ----------
    onSelectDefect(defectoId) {
        if (!this.hasSession) return;
        this.state.selectedDefectoId = defectoId;
        this.state.popupDefectId = defectoId;
        this.state.sizePopupOpen = true;
        this._saveDraft();
    }

    onSelectSize(sizeCode) {
        if (!this.hasSession || !this.popupDefect) return;

        const defect = this.state.defects.find((item) => item.defecto_id === this.popupDefect.defecto_id);
        if (!defect) return;

        const allowed = (defect.is_hueco ? HUECO_SIZE_OPTIONS : DEFECT_SIZE_OPTIONS).map((o) => o.value);
        if (!allowed.includes(String(sizeCode))) {
            this.notification.add("Tamaño inválido para este defecto.", { type: "danger" });
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

    // ---------- Resumen / Undo ----------
    getSizeBreakdown(defect) {
        const counts = {};
        for (const s of defect.sizes || []) {
            const key = String(s);
            counts[key] = (counts[key] || 0) + 1;
        }
        const options = defect.is_hueco ? HUECO_SIZE_OPTIONS : DEFECT_SIZE_OPTIONS;
        return options.filter((o) => counts[o.value]).map((o) => ({ value: o.value, label: o.label, qty: counts[o.value] }));
    }

    removeLastOccurrence(defectoId) {
        const defect = this.state.defects.find((d) => d.defecto_id === defectoId);
        if (!defect || !(defect.sizes || []).length) return;
        defect.sizes.pop();
        defect.count = defect.sizes.length;
        this._saveDraft();
    }

    clearDefect(defectoId) {
        const defect = this.state.defects.find((d) => d.defecto_id === defectoId);
        if (!defect) return;
        defect.sizes = [];
        defect.count = 0;
        if (this.state.selectedDefectoId === defectoId) this.state.selectedDefectoId = false;
        this._saveDraft();
    }

    clearAllSelections() {
        for (const d of this.state.defects || []) {
            d.sizes = [];
            d.count = 0;
        }
        this.state.selectedDefectoId = false;
        this._saveDraft();
    }

    // ---------- Finalizar ----------
    async onFinalize() {
        if (this.isFinalizeDisabled) return;

        this.state.meterPopupOpen = true;
        this._saveDraft();
    }

    closeMeterPopup() {
        this.state.meterPopupOpen = false;
        this._saveDraft();
    }

    async confirmFinalize() {
        if (this.isFinalizeDisabled) return;

        const metersValue = parsePositiveFloat(this.state.meters);
        if (metersValue <= 0) {
            this.notification.add("El metraje debe ser mayor a 0.", { type: "warning" });
            return;
        }

        this.state.submitting = true;
        this.state.error = "";
        try {
            const selections = (this.state.defects || [])
                .filter((d) => (d.sizes || []).length)
                .map((d) => ({ defecto_id: d.defecto_id, sizes: d.sizes }));

            await this.orm.call("control.apariencia.line", "action_tablet_finalize", [
                Number(this.state.selectedPartidaId),
                Number(this.state.rolloNum),
                selections,
                parsePositiveFloat(this.state.width),
                metersValue,
                Number(this.state.selectedAparienciaId),
                Number(this.state.selectedEvaluacionId || 0),
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
        const selectedAparienciaId = this.state.selectedAparienciaId;
        const selectedAparienciaData = this.state.selectedAparienciaData;
        const aparienciaQuery = selectedAparienciaData?.name ? String(selectedAparienciaData.name) : this.state.aparienciaQuery;

        this.state.aparienciaQuery = aparienciaQuery || "";
        this.state.selectedAparienciaId = selectedAparienciaId || "";
        this.state.selectedAparienciaData = selectedAparienciaData || null;
        this._syncSelectedAparienciaData();

        this.state.partidaQuery = partidaQuery || "";
        this.state.selectedPartidaId = selectedPartidaId || "";
        this.state.selectedPartidaData = selectedPartidaData || null;
        this.state.selectedEvaluacionId = this.state.selectedEvaluacionId || "";
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
        this.state.aparienciaQuery = "";
        this.state.selectedAparienciaId = "";
        this.state.selectedAparienciaData = null;
        this.state.showAparienciaDropdown = false;

        this.state.partidaQuery = "";
        this.state.selectedPartidaId = "";
        this.state.selectedPartidaData = null;
        this.state.selectedEvaluacionId = "";
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

    // ---------- UI ----------
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
        // vuelve al paso 1 sin borrar partida/rollo
        this.state.sessionActive = false;
        this.state.defects = [];
        this.state.selectedDefectoId = false;
        this.state.sizePopupOpen = false;
        this.state.popupDefectId = false;
        this._saveDraft();
    }
}

QualityDefectScreen.template = "idtx_batch_quality.QualityDefectScreen";
registry.category("actions").add("idtx_quality.defect_screen", QualityDefectScreen);