/** @odoo-module */

import { Component, onMounted, onWillStart, onWillUnmount, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

const DRAFT_STORAGE_KEY = "idtx_quality_control.solidez_lavado_screen.draft.v1";

const STEPS = [
    {
        key: "solidez_color",
        label: "Solidez del Color al Lavado",
        fields: ["cambio_color_grado"],
    },
    {
        key: "migracion",
        label: "Migracion",
        fields: [
            "mig_acetato",
            "mig_algodon",
            "mig_nylon",
            "mig_poliester",
            "mig_acrilico",
            "mig_lana",
        ],
    },
    {
        key: "frote",
        label: "Solidez del color al frote",
        fields: ["frote_seco", "frote_humedo"],
    },
];

const FIELD_LABEL = {
    cambio_color_grado: "Cambio de color grado",
    mig_acetato: "Acetato",
    mig_algodon: "Algodon",
    mig_nylon: "Nylon",
    mig_poliester: "Poliester",
    mig_acrilico: "Acrilico",
    mig_lana: "Lana",
    frote_seco: "Seco",
    frote_humedo: "Humedo",
};

function normalizeText(v) {
    return (v || "").toString().toLowerCase().trim();
}

function normalizeSpeechText(v) {
    return normalizeText(v)
        .normalize("NFD")
        .replace(/[\u0300-\u036f]/g, "")
        .replace(/\s+/g, " ")
        .trim();
}

function asFloat(v) {
    const n = Number((v || "").toString().replace(",", "."));
    return Number.isFinite(n) ? n : 0;
}

function _normalizeSpokenNumberText(rawText) {
    const unitMap = {
        cero: "0",
        un: "1",
        uno: "1",
        una: "1",
        dos: "2",
        tres: "3",
        cuatro: "4",
        cinco: "5",
        seis: "6",
        siete: "7",
        ocho: "8",
        nueve: "9",
        diez: "10",
        once: "11",
        doce: "12",
        trece: "13",
        catorce: "14",
        quince: "15",
        dieciseis: "16",
        diecisiete: "17",
        dieciocho: "18",
        diecinueve: "19",
        veinte: "20",
        veintiuno: "21",
        veintidos: "22",
        veintitres: "23",
        veinticuatro: "24",
        veinticinco: "25",
        veintiseis: "26",
        veintisiete: "27",
        veintiocho: "28",
        veintinueve: "29",
        treinta: "30",
        cuarenta: "40",
        cincuenta: "50",
        sesenta: "60",
        setenta: "70",
        ochenta: "80",
        noventa: "90",
        cien: "100",
    };

    let text = normalizeSpeechText(rawText);
    text = text.replace(/\b([a-z]+)\b/g, (word) => unitMap[word] ?? word);
    text = text.replace(/\b(\d{2})\s+y\s+(\d)\b/g, (_, tens, units) => String(Number(tens) + Number(units)));
    text = text
        .replace(/(-?\d+)\s*(?:coma|punto)\s*(\d+)/g, "$1.$2")
        .replace(/coma|punto/g, ".")
        .replace(/\s*\.\s*/g, ".");
    text = text
        .replace(/\b(?:menos|negativo)\s+(\d+)\.(\d+)\b/g, "-$1.$2")
        .replace(/\b(?:menos|negativo)\s+(\d+(?:\.\d+)?)\b/g, "-$1");
    return text;
}

function extractSpeechFloats(rawText) {
    const text = _normalizeSpokenNumberText(rawText);
    const matches = text.match(/-?\d+(?:[\.,]\d+)?/g) || [];
    return matches.map((m) => Number(m.replace(",", "."))).filter((n) => Number.isFinite(n));
}

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

function getInitialValues() {
    return {
        cambio_color_grado: "",
        mig_acetato: "",
        mig_algodon: "",
        mig_nylon: "",
        mig_poliester: "",
        mig_acrilico: "",
        mig_lana: "",
        frote_seco: "",
        frote_humedo: "",
    };
}

export class QualitySolidezLavadoScreen extends Component {
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

        this._speechRecognition = null;
        this._voiceRestartTimer = null;
        this._searchTimer = null;

        this.state = useState({
            loading: true,
            submitting: false,
            error: "",
            partidas: [],
            partidaQuery: "",
            selectedPartidaId: "",
            selectedPartidaData: null,
            showPartidaDropdown: false,
            isSearchingPartida: false,
            values: getInitialValues(),
            currentStep: 0,
            inEvaluation: false,
            voiceSupported: false,
            voiceActive: false,
            voiceShouldStayOn: false,
            voiceError: "",
            voiceTranscript: "",
        });

        onWillStart(async () => {
            this._restoreDraft();
            await this.loadPartidas();
            this._syncSelectedPartidaData();
        });

        onMounted(() => this._initVoiceRecognition());

        onWillUnmount(() => {
            this._stopVoiceRecognition();
            if (this._voiceRestartTimer) clearTimeout(this._voiceRestartTimer);
            if (this._searchTimer) clearTimeout(this._searchTimer);
            this._saveDraft();
        });
    }

    get activeStep() {
        return STEPS[this.state.currentStep] || STEPS[0];
    }

    get filteredPartidas() {
        const q = normalizeText(this.state.partidaQuery);
        if (!q) return (this.state.partidas || []).slice(0, 25);
        return (this.state.partidas || [])
            .filter((p) =>
                normalizeText(p.batch).includes(q) ||
                normalizeText(p.customer).includes(q) ||
                normalizeText(p.article).includes(q) ||
                normalizeText(p.color_name).includes(q)
            )
            .slice(0, 25);
    }

    get isLastStep() {
        return this.state.currentStep >= (STEPS.length - 1);
    }

    get canFinalizeEvaluation() {
        if (!this.state.selectedPartidaId || this.state.submitting) return false;
        for (const step of STEPS) {
            for (const fieldName of step.fields) {
                if (`${this.state.values[fieldName] || ""}`.trim() === "") {
                    return false;
                }
            }
        }
        return true;
    }

    getStepFieldLabel(fieldName) {
        return FIELD_LABEL[fieldName] || fieldName;
    }

    _saveDraft() {
        const draft = {
            partidaQuery: this.state.partidaQuery,
            selectedPartidaId: this.state.selectedPartidaId,
            values: this.state.values,
            currentStep: this.state.currentStep,
            inEvaluation: this.state.inEvaluation,
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
        try {
            const draft = JSON.parse(raw);
            if (!draft || typeof draft !== "object") return;
            this.state.partidaQuery = draft.partidaQuery || "";
            this.state.selectedPartidaId = draft.selectedPartidaId || "";
            this.state.values = { ...getInitialValues(), ...(draft.values || {}) };
            this.state.currentStep = Number.isInteger(draft.currentStep)
                ? Math.max(0, Math.min(draft.currentStep, STEPS.length - 1))
                : 0;
            this.state.inEvaluation = Boolean(draft.inEvaluation);
        } catch {
            // ignore
        }
    }

    _syncSelectedPartidaData() {
        if (!this.state.selectedPartidaId) {
            this.state.selectedPartidaData = null;
            return;
        }
        const found = (this.state.partidas || []).find((p) => `${p.id}` === `${this.state.selectedPartidaId}`);
        this.state.selectedPartidaData = found || null;
        if (found?.batch) this.state.partidaQuery = found.batch;
    }

    async loadPartidas(query = "") {
        this.state.loading = true;
        this.state.error = "";
        try {
            this.state.partidas = await this.orm.call("qc.wash.fastness.eval", "action_tablet_get_partidas", [query, 100]);
            this._syncSelectedPartidaData();
        } catch (error) {
            this.state.error = extractRpcMessage(error, "No se pudieron cargar las partidas.");
        } finally {
            this.state.loading = false;
        }
    }

    onPartidaQueryInput(ev) {
        const value = ev.target.value || "";
        this.state.partidaQuery = value;
        if (this.state.selectedPartidaId) {
            const batch = this.state.selectedPartidaData?.batch || "";
            if (value !== batch) {
                this.state.selectedPartidaId = "";
                this.state.selectedPartidaData = null;
            }
        }
        this.state.showPartidaDropdown = Boolean(value) && !this.state.selectedPartidaId;
        this._saveDraft();
        if (this._searchTimer) clearTimeout(this._searchTimer);
        this._searchTimer = setTimeout(() => this.searchPartidas(value), 250);
    }

    onPartidaInputFocus() {
        if (!this.state.selectedPartidaId && this.state.partidaQuery) {
            this.state.showPartidaDropdown = true;
        }
    }

    async searchPartidas(query) {
        this.state.isSearchingPartida = true;
        try {
            await this.loadPartidas((query || "").trim());
        } finally {
            this.state.isSearchingPartida = false;
        }
    }

    selectPartida(partidaId) {
        this.state.selectedPartidaId = String(partidaId);
        this._syncSelectedPartidaData();
        this.state.showPartidaDropdown = false;
        this.state.inEvaluation = false;
        this._saveDraft();
    }

    startEvaluation() {
        if (!this.state.selectedPartidaId || this.state.submitting) return;
        this.state.inEvaluation = true;
        this.state.currentStep = 0;
        this._saveDraft();
    }

    clearPartida() {
        this.state.selectedPartidaId = "";
        this.state.selectedPartidaData = null;
        this.state.partidaQuery = "";
        this.state.values = getInitialValues();
        this.state.currentStep = 0;
        this.state.inEvaluation = false;
        this._saveDraft();
    }

    onFieldChange(fieldName, ev) {
        this.state.values[fieldName] = (ev.target.value || "").replace(",", ".");
        this._saveDraft();
    }

    nextStep() {
        if (this.state.currentStep < STEPS.length - 1) {
            this.state.currentStep += 1;
            this.state.voiceError = "";
            this._saveDraft();
        }
    }

    previousStep() {
        if (this.state.currentStep > 0) {
            this.state.currentStep -= 1;
            this.state.voiceError = "";
            this._saveDraft();
            return;
        }
        this.onBackToSearch();
    }

    _initVoiceRecognition() {
        const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
        if (!SpeechRecognition) {
            this.state.voiceSupported = false;
            this.state.voiceError = "Dictado no disponible en este navegador.";
            return;
        }

        this.state.voiceSupported = true;
        const recognition = new SpeechRecognition();
        recognition.lang = "es-PE";
        recognition.continuous = true;
        recognition.interimResults = false;
        recognition.maxAlternatives = 1;

        recognition.onstart = () => {
            this.state.voiceActive = true;
            this.state.voiceError = "";
        };

        recognition.onresult = (event) => {
            let finalText = "";
            for (let i = event.resultIndex; i < event.results.length; i++) {
                if (event.results[i].isFinal) finalText += `${event.results[i][0].transcript} `;
            }
            finalText = finalText.trim();
            if (!finalText) return;
            this.state.voiceTranscript = finalText;
            this._processVoiceCommand(finalText);
        };

        recognition.onend = () => {
            if (!this.state.voiceShouldStayOn) {
                this.state.voiceActive = false;
                return;
            }
            this._scheduleVoiceRestart();
        };

        recognition.onerror = (event) => {
            const code = event?.error || "unknown";
            this.state.voiceError = this._describeVoiceError(code);
            if (!this.state.voiceShouldStayOn) {
                this.state.voiceActive = false;
                return;
            }
            if (code === "not-allowed" || code === "service-not-allowed" || code === "audio-capture") {
                this.state.voiceShouldStayOn = false;
                this.state.voiceActive = false;
                this.notification.add(this.state.voiceError, { type: "danger" });
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
        if (this.state.voiceActive) {
            this._stopVoiceRecognition();
            return;
        }
        this._startVoiceRecognition();
    }

    async _startVoiceRecognition() {
        if (!this._speechRecognition) return;

        if (!window.isSecureContext) {
            this.state.voiceError = "El dictado requiere un contexto seguro (HTTPS o localhost).";
            this.notification.add(this.state.voiceError, { type: "warning" });
        }

        this.state.voiceError = "";
        this.state.voiceShouldStayOn = true;
        try {
            this._speechRecognition.start();
            this.state.voiceActive = true;
        } catch (error) {
            this.state.voiceShouldStayOn = false;
            this.state.voiceActive = false;
            this.state.voiceError = `No se pudo iniciar el dictado: ${error?.message || "error desconocido"}`;
            this.notification.add(this.state.voiceError, { type: "danger" });
        }
    }

    _stopVoiceRecognition() {
        this.state.voiceShouldStayOn = false;
        this.state.voiceActive = false;
        if (this._voiceRestartTimer) clearTimeout(this._voiceRestartTimer);
        if (this._speechRecognition) {
            try {
                this._speechRecognition.stop();
            } catch {
                // ignore
            }
        }
    }

    _scheduleVoiceRestart() {
        if (!this.state.voiceShouldStayOn) return;
        if (this._voiceRestartTimer) clearTimeout(this._voiceRestartTimer);
        this._voiceRestartTimer = setTimeout(() => {
            if (!this.state.voiceShouldStayOn) return;
            try {
                this._speechRecognition.start();
                this.state.voiceActive = true;
            } catch {
                this.state.voiceActive = false;
                this.state.voiceError = "No se pudo reactivar el dictado.";
            }
        }, 350);
    }

    _describeVoiceError(code) {
        if (code === "not-allowed" || code === "service-not-allowed") {
            return "El navegador bloqueo el microfono para dictado.";
        }
        if (code === "audio-capture") {
            return "No se encontro un microfono disponible.";
        }
        if (code === "network") {
            return "Fallo de red durante el reconocimiento de voz.";
        }
        if (code === "no-speech") {
            return "No se detecto voz. Intente hablar mas cerca del microfono.";
        }
        if (code === "aborted") {
            return "Dictado interrumpido. Intentando reanudar...";
        }
        return "Error de reconocimiento de voz.";
    }

    _processVoiceCommand(rawText) {
        if (!this.state.inEvaluation) {
            this.state.voiceError = "Primero seleccione partida y comience evaluacion.";
            return;
        }

        const text = normalizeSpeechText(rawText);

        if (/\b(detener|parar|silencio)\b/.test(text)) {
            this._stopVoiceRecognition();
            return;
        }

        if (/\blimpiar\s+todo\b/.test(text)) {
            this._clearAllActiveFields();
            this._saveDraft();
            return;
        }

        if (/\b(limpiar|borra?r?)\b/.test(text)) {
            this._clearLastFilledField();
            this._saveDraft();
            return;
        }

        if (/\bsiguiente\b/.test(text)) {
            this.nextStep();
            this._saveDraft();
            return;
        }

        if (/\banterior\b/.test(text)) {
            this.previousStep();
            this._saveDraft();
            return;
        }

        const numbers = extractSpeechFloats(rawText);
        if (!numbers.length) {
            this.state.voiceError = "No se detectaron numeros en el dictado.";
            return;
        }

        const assigned = this._assignNumbersToNextFields(numbers);
        if (!assigned) {
            this.state.voiceError = "Este paso ya esta completo. Diga limpiar o siguiente.";
            return;
        }

        this.state.voiceError = "";
        const needed = this.activeStep.fields.length;
        const filled = this._countFilledActiveFields();
        this.state.voiceTranscript = `${rawText} [+${assigned}] [${filled}/${needed}]`;
        this._saveDraft();
    }

    _assignNumbersToNextFields(numbers) {
        const fields = this.activeStep.fields || [];
        let assigned = 0;
        for (const value of numbers) {
            const idx = fields.findIndex((fieldName) => `${this.state.values[fieldName] || ""}`.trim() === "");
            if (idx === -1) break;
            this.state.values[fields[idx]] = `${value}`;
            assigned += 1;
        }
        return assigned;
    }

    _clearLastFilledField() {
        const fields = this.activeStep.fields || [];
        for (let i = fields.length - 1; i >= 0; i--) {
            const fieldName = fields[i];
            if (`${this.state.values[fieldName] || ""}`.trim() !== "") {
                this.state.values[fieldName] = "";
                this.state.voiceError = "";
                const filled = this._countFilledActiveFields();
                this.state.voiceTranscript = `limpiar [${filled}/${fields.length}]`;
                return;
            }
        }
        this.state.voiceError = "No hay datos para limpiar en este paso.";
    }

    _clearAllActiveFields() {
        const fields = this.activeStep.fields || [];
        for (const fieldName of fields) {
            this.state.values[fieldName] = "";
        }
        this.state.voiceError = "";
        this.state.voiceTranscript = `limpiar todo [0/${fields.length}]`;
    }

    _countFilledActiveFields() {
        const fields = this.activeStep.fields || [];
        return fields.filter((fieldName) => `${this.state.values[fieldName] || ""}`.trim() !== "").length;
    }

    async finalizeEvaluation() {
        if (!this.canFinalizeEvaluation) {
            this.notification.add("Complete todos los campos antes de finalizar.", { type: "warning" });
            return;
        }

        if (!window.confirm("Desea finalizar y registrar esta evaluacion?")) {
            return;
        }

        const payload = {};
        for (const fieldName of Object.keys(this.state.values)) {
            payload[fieldName] = asFloat(this.state.values[fieldName]);
        }

        this.state.submitting = true;
        this.state.error = "";
        try {
            const result = await this.orm.call("qc.wash.fastness.eval", "action_tablet_finalize", [
                Number(this.state.selectedPartidaId),
                payload,
            ]);
            this.notification.add(`Evaluacion registrada en ${result?.name || "evaluacion"}.`, { type: "success" });
            await this.onBackToSearch();
        } catch (error) {
            this.state.error = extractRpcMessage(error, "No se pudo finalizar la evaluacion.");
            this.notification.add(this.state.error, { type: "warning" });
        } finally {
            this.state.submitting = false;
        }
    }

    async onBackToSearch() {
        this._stopVoiceRecognition();
        this.clearPartida();
        this.state.error = "";
        this.state.showPartidaDropdown = false;
        this.state.inEvaluation = false;
        this._saveDraft();
    }

    async close() {
        this._stopVoiceRecognition();
        this._saveDraft();
        if (window.history.length > 1) {
            window.history.back();
            return;
        }
        await this.homeMenu.toggle();
    }
}

QualitySolidezLavadoScreen.template = "idtx_quality_control.QualitySolidezLavadoScreen";
registry.category("actions").add("idtx_quality_control.solidez_lavado_screen", QualitySolidezLavadoScreen);
