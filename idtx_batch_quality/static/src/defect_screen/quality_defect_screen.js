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

const VOICE_STOPWORDS = new Set([
    "de", "del", "la", "las", "el", "los", "y", "en", "con", "por", "para", "un", "una",
    "falla", "falla", "defecto", "defectos", "tamano", "tamaño", "numero", "n", "size",
]);

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

function normalizeSpeechText(v) {
    return normalizeText(v)
        .normalize("NFD")
        .replace(/[\u0300-\u036f]/g, "")
        // Homogeneiza confusiones frecuentes de voz: ll <-> y
        .replace(/ll/g, "y")
        .replace(/[^a-z0-9\s\.]/g, " ")
        .replace(/\s+/g, " ")
        .trim();
}

function singularToken(token) {
    if (!token) return token;
    if (token.endsWith("es") && token.length > 4) return token.slice(0, -2);
    if (token.endsWith("s") && token.length > 3) return token.slice(0, -1);
    return token;
}

function voiceTokens(v) {
    return normalizeSpeechText(v)
        .split(" ")
        .map((t) => singularToken(t))
        .filter((t) => t.length >= 3 && !VOICE_STOPWORDS.has(t));
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
        this._speechRecognition = null;
        this._voiceRestartTimer = null;
        this._voiceRestartAttempts = 0;
        this._voiceAudioCtx = null;

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

            // Voice input
            voiceSupported: false,
            voiceActive: false,
            voiceTranscript: "",
            voiceShouldStayOn: false,
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
            this._initVoiceRecognition();

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
            this._stopVoiceRecognition();
            if (this._voiceRestartTimer) {
                clearTimeout(this._voiceRestartTimer);
                this._voiceRestartTimer = null;
            }
            if (this._voiceAudioCtx) {
                try {
                    this._voiceAudioCtx.close();
                } catch {
                    // ignore
                }
                this._voiceAudioCtx = null;
            }
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

    _resolveAparienciaIdFromState() {
        const fromId = Number(this.state.selectedAparienciaId || 0);
        if (fromId > 0) return fromId;

        const fromDataId = Number(this.state.selectedAparienciaData?.id || 0);
        if (fromDataId > 0) return fromDataId;

        const selectedName = String(this.state.selectedAparienciaData?.name || "").trim();
        if (!selectedName) return 0;

        const byName = (this.state.apariencias || []).find((a) => String(a?.name || "").trim() === selectedName);
        return Number(byName?.id || 0);
    }

    _resolveAparienciaIdFromDom() {
        if (!this.el) return 0;
        const selectEl = this.el.querySelector(".o_qds_apariencia_select");
        return Number(selectEl?.value || 0);
    }

    _ensureResolvedAparienciaSelection() {
        let aparienciaId = this._resolveAparienciaIdFromState();
        if (!aparienciaId) {
            aparienciaId = this._resolveAparienciaIdFromDom();
        }
        if (!aparienciaId) return 0;

        this.state.selectedAparienciaId = String(aparienciaId);
        const found = (this.state.apariencias || []).find((a) => Number(a?.id || 0) === aparienciaId);
        if (found) {
            this.state.selectedAparienciaData = found;
        }
        return aparienciaId;
    }

    get canProceedBasics() {
        return (
            Boolean(this._resolveAparienciaIdFromState()) &&
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

    get canUseVoice() {
        return this.hasSession && this.state.voiceSupported && !this.state.submitting;
    }

    get selectedDefects() {
        return (this.state.defects || []).filter((d) => (d.sizes || []).length);
    }

    // Rollo aparece SOLO cuando ya se seleccionó una partida (y aún no empezó captura)
    get shouldShowRolloInput() {
        return Boolean(this._resolveAparienciaIdFromState()) && Boolean(this.state.selectedPartidaId) && !this.hasSession;
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

    get selectedPartidaEvaluatedRollGroups() {
        const groups = Array.isArray(this.state.selectedPartidaData?.evaluated_roll_groups)
            ? [...this.state.selectedPartidaData.evaluated_roll_groups]
            : [];
        const selectedAparienciaId = Number(this.state.selectedAparienciaId || 0);
        groups.sort((left, right) => {
            const leftSelected = Number(left?.apariencia_id || 0) === selectedAparienciaId ? 0 : 1;
            const rightSelected = Number(right?.apariencia_id || 0) === selectedAparienciaId ? 0 : 1;
            if (leftSelected !== rightSelected) {
                return leftSelected - rightSelected;
            }
            return String(left?.apariencia_name || "").localeCompare(String(right?.apariencia_name || ""));
        });
        return groups;
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
        const value = String(event.target.value || "");
        this.state.selectedAparienciaId = value;
        if (!value) {
            this.state.selectedAparienciaData = null;
        }
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
        const aparienciaId = Number(this._ensureResolvedAparienciaSelection() || 0);

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
                [pedidoLineId, rolloNum, aparienciaId, Number(this.state.selectedEvaluacionId || 0)],
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
        const aparienciaId = this._ensureResolvedAparienciaSelection();

        if (!aparienciaId) {
            this.notification.add("Seleccione un control de apariencia.", { type: "warning" });
            return;
        }
        if (!this.state.selectedPartidaId) {
            this.notification.add("Seleccione una partida.", { type: "warning" });
            return;
        }

        if (Number(this.state.rolloNum) <= 0) {
            this.notification.add("Ingrese un numero de rollo valido.", { type: "warning" });
            return;
        }

        if (parsePositiveFloat(this.state.width) <= 0) {
            this.notification.add("Ingrese un ancho valido.", { type: "warning" });
            return;
        }

        if (this.state.submitting || this.state.isCheckingRollo || this.state.rolloValidationError) {
            return;
        }

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
                    aparienciaId,
                    Number(this.state.selectedEvaluacionId || 0),
                ],
                { context: { appearance_type: "quality" } }
            );
            this.state.selectedEvaluacionId = evaluacion?.id ? String(evaluacion.id) : "";

            const defects = await this.orm.call(
                "control.apariencia.line",
                "action_tablet_get_defectos",
                [aparienciaId],
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

    // ---------- Voz ----------
    _initVoiceRecognition() {
        const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
        if (!SpeechRecognition) {
            this.state.voiceSupported = false;
            return;
        }

        this.state.voiceSupported = true;
        const recognition = new SpeechRecognition();
        recognition.lang = "es-PE";
        recognition.continuous = true;
        recognition.interimResults = false;

        recognition.onresult = (event) => {
            this._voiceRestartAttempts = 0;
            let finalText = "";
            for (let i = event.resultIndex; i < event.results.length; i++) {
                if (event.results[i].isFinal) {
                    finalText += `${event.results[i][0].transcript} `;
                }
            }
            finalText = finalText.trim();
            if (!finalText) return;
            this.state.voiceTranscript = finalText;
            this._processVoiceCommand(finalText);
        };

        recognition.onerror = (event) => {
            // Algunos navegadores cortan reconocimiento por limite interno de sesion.
            // Reintentamos en errores recuperables mientras la sesion de voz siga activa.
            if (!this.state.voiceShouldStayOn || !this.canUseVoice) {
                this.state.voiceActive = false;
                return;
            }

            const code = event?.error || "";
            const fatal = ["not-allowed", "service-not-allowed", "audio-capture"];
            if (fatal.includes(code)) {
                this.state.voiceActive = false;
                this.state.voiceShouldStayOn = false;
                this.notification.add("No se pudo continuar con voz. Verifique permisos del micrófono.", { type: "warning" });
                return;
            }

            this._scheduleVoiceRestart();
        };

        recognition.onend = () => {
            // Mantener escucha continua mientras la sesion de voz siga activa.
            if (!this.state.voiceShouldStayOn || !this.canUseVoice) {
                this.state.voiceActive = false;
                return;
            }
            this._scheduleVoiceRestart();
        };

        this._speechRecognition = recognition;
    }

    toggleVoiceInput() {
        if (!this.state.voiceSupported) {
            this.notification.add("Este navegador no soporta reconocimiento de voz.", { type: "warning" });
            return;
        }
        if (!this.hasSession) {
            this.notification.add("Primero inicie la captura de defectos.", { type: "warning" });
            return;
        }
        if (this.state.voiceActive) {
            this._stopVoiceRecognition();
            this.notification.add("Micrófono desactivado.", { type: "info" });
        } else {
            this._startVoiceRecognition();
            this.notification.add("Micrófono activado. Puede decir defecto y tamaño.", { type: "success" });
        }
    }

    _startVoiceRecognition() {
        if (!this._speechRecognition || !this.canUseVoice) return;
        this.state.voiceShouldStayOn = true;
        this._voiceRestartAttempts = 0;
        this.state.voiceActive = true;
        this._ensureVoiceAudioContext();
        try {
            this._speechRecognition.start();
        } catch {
            // ignore repeated start errors
        }
    }

    _stopVoiceRecognition() {
        this.state.voiceShouldStayOn = false;
        this.state.voiceActive = false;
        this._voiceRestartAttempts = 0;
        if (this._voiceRestartTimer) {
            clearTimeout(this._voiceRestartTimer);
            this._voiceRestartTimer = null;
        }
        if (this._speechRecognition) {
            try {
                this._speechRecognition.stop();
            } catch {
                // ignore stop errors
            }
        }
    }

    _scheduleVoiceRestart() {
        if (!this.state.voiceShouldStayOn || !this.canUseVoice) {
            this.state.voiceActive = false;
            return;
        }
        if (this._voiceRestartTimer) {
            clearTimeout(this._voiceRestartTimer);
        }

        const delay = Math.min(1200, 250 + this._voiceRestartAttempts * 150);
        this._voiceRestartAttempts += 1;
        this._voiceRestartTimer = setTimeout(() => {
            if (!this.state.voiceShouldStayOn || !this.canUseVoice) {
                this.state.voiceActive = false;
                return;
            }
            try {
                this._speechRecognition.start();
                this.state.voiceActive = true;
            } catch {
                this.state.voiceActive = false;
            }
        }, delay);
    }

    _processVoiceCommand(rawText) {
        if (!this.hasSession) return;

        const text = normalizeSpeechText(rawText);
        if (/\b(finalizar|terminar)\b/.test(text)) {
            this._stopVoiceRecognition();
            this.onFinalize();
            this._playVoiceCue("ok");
            this.notification.add("Comando de voz: finalizar.", { type: "info" });
            return;
        }

        if (/\b(detener|parar)\b/.test(text) && /\b(microfono|micro|voz)\b/.test(text)) {
            this._stopVoiceRecognition();
            this.notification.add("Micrófono desactivado por voz.", { type: "info" });
            return;
        }

        const defect = this._findDefectByVoice(text);
        const popupDefect = this.popupDefect;

        // Si no encontró defecto, permitimos usar solo tamaño sobre popup abierto.
        if (!defect && this.state.sizePopupOpen && popupDefect) {
            const sizeOnlyList = this._extractSizesFromVoice(text, popupDefect);
            if (sizeOnlyList.length) {
                for (const sizeCode of sizeOnlyList) {
                    this.onSelectDefect(popupDefect.defecto_id);
                    this.onSelectSize(sizeCode);
                }
                this._playVoiceCue("ok");
                this.notification.add(`Registrado por voz: ${popupDefect.name} (${sizeOnlyList.join(", ")}).`, { type: "success" });
                return;
            }
        }

        if (!defect) {
            this._playVoiceCue("error");
            this.notification.add(`No reconocí el defecto en: "${rawText}"`, { type: "warning" });
            return;
        }

        const sizeCodes = this._extractSizesFromVoice(text, defect);
        if (!sizeCodes.length) {
            if (this._hasInvalidSizeMention(text, defect)) {
                this._playVoiceCue("error");
                this.notification.add(`No encontré ese tamaño para ${defect.name}.`, { type: "warning" });
                return;
            }
            this.onSelectDefect(defect.defecto_id);
            this.notification.add(`Defecto reconocido: ${defect.name}. Ahora diga el tamaño.`, { type: "info" });
            return;
        }

        // Pattern support: "2 ancho variado 4" => register size 4 twice.
        let quantity = this._extractQuantityFromVoice(text, defect);
        let finalSizeCodes = [...sizeCodes];

        // Shorthand support: "4 variado 4" (qty + defect token + size)
        if (this._looksLikeQtyDefectSizePattern(text) && finalSizeCodes.length) {
            const leadQty = this._extractLeadingQuantity(text);
            if (leadQty > 1) {
                quantity = leadQty;
                finalSizeCodes = [finalSizeCodes[finalSizeCodes.length - 1]];
            }
        }

        if (quantity > 1 && finalSizeCodes.length === 1) {
            while (finalSizeCodes.length < quantity) {
                finalSizeCodes.push(finalSizeCodes[0]);
            }
        }

        for (const sizeCode of finalSizeCodes) {
            this.onSelectDefect(defect.defecto_id);
            this.onSelectSize(sizeCode);
        }
        this._playVoiceCue("ok");
        this.notification.add(`Registrado por voz: ${defect.name} (${finalSizeCodes.join(", ")}).`, { type: "success" });
    }

    _ensureVoiceAudioContext() {
        if (this._voiceAudioCtx) return this._voiceAudioCtx;
        const Ctx = window.AudioContext || window.webkitAudioContext;
        if (!Ctx) return null;
        try {
            this._voiceAudioCtx = new Ctx();
        } catch {
            this._voiceAudioCtx = null;
        }
        return this._voiceAudioCtx;
    }

    _playVoiceCue(type) {
        const ctx = this._ensureVoiceAudioContext();
        if (!ctx) return;

        if (ctx.state === "suspended") {
            try {
                ctx.resume();
            } catch {
                return;
            }
        }

        const now = ctx.currentTime;

        const tone = (freq, start, duration, gain = 0.045, wave = "sine") => {
            const osc = ctx.createOscillator();
            const vol = ctx.createGain();
            osc.type = wave;
            osc.frequency.value = freq;
            vol.gain.setValueAtTime(0.0001, start);
            vol.gain.exponentialRampToValueAtTime(gain, start + 0.01);
            vol.gain.exponentialRampToValueAtTime(0.0001, start + duration);
            osc.connect(vol);
            vol.connect(ctx.destination);
            osc.start(start);
            osc.stop(start + duration + 0.01);
        };

        if (type === "ok") {
            // Exito: doble tono agudo corto
            tone(1200, now, 0.07, 0.05, "triangle");
            tone(1600, now + 0.09, 0.09, 0.05, "triangle");
            return;
        }

        // Error/no reconocido: dos tonos graves largos (claramente distinto)
        tone(260, now, 0.18, 0.06, "square");
        tone(180, now + 0.22, 0.22, 0.06, "square");
    }

    _findDefectByVoice(text) {
        const defects = this.state.defects || [];
        if (!defects.length) return null;

        const normalizedDefects = defects.map((d) => ({
            defect: d,
            name: normalizeSpeechText(d.name),
            tokens: voiceTokens(d.name),
        }));

        const textTokens = voiceTokens(text);
        const textTokenSet = new Set(textTokens);

        // 1) Coincidencia directa por nombre completo
        const directMatches = normalizedDefects
            .filter((d) => d.name && text.includes(d.name))
            .sort((a, b) => b.name.length - a.name.length);
        if (directMatches.length) {
            return directMatches[0].defect;
        }

        // 1.1) Token distintivo unico: si el usuario dice una palabra clave unica.
        const tokenToDefects = new Map();
        for (const d of normalizedDefects) {
            for (const tk of d.tokens) {
                if (!tokenToDefects.has(tk)) tokenToDefects.set(tk, []);
                tokenToDefects.get(tk).push(d);
            }
        }
        for (const tk of textTokenSet) {
            const owners = tokenToDefects.get(tk) || [];
            if (owners.length === 1) {
                return owners[0].defect;
            }
        }

        // 2) Coincidencia por superposición de tokens
        let best = null;
        let bestScore = 0;
        let bestCommon = 0;
        for (const d of normalizedDefects) {
            const tokens = d.tokens || [];
            if (!tokens.length) continue;

            let common = 0;
            for (const tk of tokens) {
                const matched = textTokens.some((spoken) => this._voiceTokenMatch(spoken, tk));
                if (matched) common++;
            }

            const score = common / tokens.length;
            if ((score > bestScore || (score === bestScore && common > bestCommon)) && score >= 0.34 && common >= 1) {
                bestScore = score;
                bestCommon = common;
                best = d.defect;
            }
        }
        return best;
    }

    _voiceTokenMatch(spoken, target) {
        if (!spoken || !target) return false;
        if (spoken === target) return true;
        if (spoken.length >= 5 && target.length >= 5) {
            if (spoken.startsWith(target) || target.startsWith(spoken)) return true;
        }
        return false;
    }

    _extractSizeFromVoice(text, defect) {
        const all = this._extractSizesFromVoice(text, defect);
        return all.length ? all[0] : null;
    }

    _extractSizesFromVoice(text, defect) {
        const allowed = (defect?.is_hueco ? HUECO_SIZE_OPTIONS : DEFECT_SIZE_OPTIONS).map((o) => o.value);

        const numberWords = {
            uno: "1",
            una: "1",
            dos: "2",
            tres: "3",
            cuatro: "4",
        };

        const out = [];
        const addIfAllowed = (value) => {
            const code = numberWords[value] || value;
            if (allowed.includes(code)) {
                out.push(code);
            }
        };

        // Prefer sizes spoken after the recognized defect name.
        const defectName = normalizeSpeechText(defect?.name || "");
        if (defectName && text.includes(defectName)) {
            const afterDefect = text.split(defectName).slice(1).join(" ").trim();
            if (afterDefect) {
                const afterMatches = afterDefect.match(/\b(1|2|3|4|uno|una|dos|tres|cuatro)\b/g) || [];
                const afterOut = [];
                for (const m of afterMatches) {
                    const code = numberWords[m] || m;
                    if (allowed.includes(code)) {
                        afterOut.push(code);
                    }
                }
                if (afterOut.length) return afterOut;
            }
        }

        // Captura listas: "tamano 1, 2 y 3", "size 2 y 4", etc.
        const listAfterSize = text.match(/(?:tamano|tamaño|size)\s*(?:numero|n)?\s*([\w\s,\.y]+)/);
        if (listAfterSize && listAfterSize[1]) {
            const matches = listAfterSize[1].match(/\b(1|2|3|4|uno|una|dos|tres|cuatro)\b/g) || [];
            for (const m of matches) addIfAllowed(m);
            if (out.length) return out;
        }

        const explicitMatch = text.match(/(?:tamano|tamaño|size)\s*(?:numero|n)?\s*(1|2|3|4|uno|una|dos|tres|cuatro)\b/);
        if (explicitMatch) {
            addIfAllowed(explicitMatch[1]);
            if (out.length) return out;
        }

        const directNumMatches = text.match(/\b(1|2|3|4|uno|una|dos|tres|cuatro)\b/g) || [];
        const shorthandQtySize = this._looksLikeQtyDefectSizePattern(text);
        if (shorthandQtySize && directNumMatches.length >= 2) {
            // Example: "4 variado 4" => first is quantity, last is size.
            addIfAllowed(directNumMatches[directNumMatches.length - 1]);
            if (out.length) return out;
        }
        for (const m of directNumMatches) {
            addIfAllowed(m);
        }
        if (out.length) return out;

        if (defect?.is_hueco) {
            if (/hasta\s*3|menor|menor\s*igual|pequeno|pequeno/.test(text) && allowed.includes("2")) return ["2"];
            if (/mas\s*de\s*3|mayor\s*de\s*3|grande/.test(text) && allowed.includes("4")) return ["4"];
        } else {
            if (/7\.5|siete/.test(text) && allowed.includes("1")) return ["1"];
            if (/15|quince/.test(text) && allowed.includes("2")) return ["2"];
            if (/23|veintitres|veinte\s*y\s*tres/.test(text) && allowed.includes("3")) return ["3"];
            if (/mas\s*de\s*23|mayor\s*de\s*23/.test(text) && allowed.includes("4")) return ["4"];
        }

        return [];
    }

    _extractQuantityFromVoice(text, defect) {
        if (!text || !defect?.name) return 1;

        const numberWords = {
            uno: 1,
            una: 1,
            dos: 2,
            tres: 3,
            cuatro: 4,
            cinco: 5,
            seis: 6,
            siete: 7,
            ocho: 8,
            nueve: 9,
            diez: 10,
        };

        const defectName = normalizeSpeechText(defect.name);
        const idx = text.indexOf(defectName);
        if (idx <= 0) return 1;

        const beforeDefect = text.slice(0, idx).trim();
        const m = beforeDefect.match(/\b(\d+|uno|una|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez)\b\s*$/);
        if (!m) return 1;

        const raw = m[1];
        const value = Number.isFinite(Number(raw)) ? Number(raw) : (numberWords[raw] || 1);
        return Math.max(1, Math.min(20, value));
    }

    _extractLeadingQuantity(text) {
        if (!text) return 1;
        const numberWords = {
            uno: 1,
            una: 1,
            dos: 2,
            tres: 3,
            cuatro: 4,
            cinco: 5,
            seis: 6,
            siete: 7,
            ocho: 8,
            nueve: 9,
            diez: 10,
        };
        const m = text.match(/^\s*(\d+|uno|una|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez)\b/);
        if (!m) return 1;
        const raw = m[1];
        const value = Number.isFinite(Number(raw)) ? Number(raw) : (numberWords[raw] || 1);
        return Math.max(1, Math.min(20, value));
    }

    _looksLikeQtyDefectSizePattern(text) {
        if (!text) return false;
        if (/(tamano|tamaño|size)\b/.test(text)) return false;
        const nums = text.match(/\b(\d+|uno|una|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez)\b/g) || [];
        // Short commands typically come as qty + defect words + size.
        return nums.length >= 2;
    }

    _hasInvalidSizeMention(text, defect) {
        if (!text) return false;

        // Si el usuario menciona explicitamente "tamano/size" con un valor fuera de rango, lo tratamos como invalido.
        const tagged = text.match(/(?:tamano|tamaño|size)\s*(?:numero|n)?\s*(\d+)/);
        if (tagged) {
            const n = Number(tagged[1]);
            const allowed = new Set((defect?.is_hueco ? HUECO_SIZE_OPTIONS : DEFECT_SIZE_OPTIONS).map((o) => Number(o.value)));
            return Number.isFinite(n) && n > 0 && !allowed.has(n);
        }

        // Caso "anillado 5": hay un numero suelto no soportado para tamanos de voz.
        const anyNum = text.match(/\b(\d+)\b/);
        if (!anyNum) return false;
        const n = Number(anyNum[1]);
        return Number.isFinite(n) && n >= 5;
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
        this._stopVoiceRecognition();
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
        this._stopVoiceRecognition();
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
        this._stopVoiceRecognition();
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
        this._stopVoiceRecognition();
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