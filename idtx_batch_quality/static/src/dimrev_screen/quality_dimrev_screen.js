/** @odoo-module */

import { Component, onMounted, onWillStart, onWillUnmount, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

const DRAFT_STORAGE_KEY = "idtx_batch_quality.dimrev_screen.draft.v2";

const STEPS = [
    {
        key: "est_l1_ancho",
        label: "Estabilidad % Ancho - 1er Lavado",
        speak: "Estabilidad primer lavado, porcentaje ancho. Dicte tres datos de muestra 1 y tres datos de muestra 2.",
        fields: [
            "st_l1_a_m1_d1", "st_l1_a_m1_d2", "st_l1_a_m1_d3",
            "st_l1_a_m2_d1", "st_l1_a_m2_d2", "st_l1_a_m2_d3",
        ],
    },
    {
        key: "est_l1_largo",
        label: "Estabilidad % Largo - 1er Lavado",
        speak: "Estabilidad primer lavado, porcentaje largo. Dicte tres datos de muestra 1 y tres datos de muestra 2.",
        fields: [
            "st_l1_l_m1_d1", "st_l1_l_m1_d2", "st_l1_l_m1_d3",
            "st_l1_l_m2_d1", "st_l1_l_m2_d2", "st_l1_l_m2_d3",
        ],
    },
    {
        key: "est_l3_ancho",
        label: "Estabilidad % Ancho - 3er Lavado",
        speak: "Estabilidad tercer lavado, porcentaje ancho. Dicte tres datos de muestra 1 y tres datos de muestra 2.",
        fields: [
            "st_l3_a_m1_d1", "st_l3_a_m1_d2", "st_l3_a_m1_d3",
            "st_l3_a_m2_d1", "st_l3_a_m2_d2", "st_l3_a_m2_d3",
        ],
    },
    {
        key: "est_l3_largo",
        label: "Estabilidad % Largo - 3er Lavado",
        speak: "Estabilidad tercer lavado, porcentaje largo. Dicte tres datos de muestra 1 y tres datos de muestra 2.",
        fields: [
            "st_l3_l_m1_d1", "st_l3_l_m1_d2", "st_l3_l_m1_d3",
            "st_l3_l_m2_d1", "st_l3_l_m2_d2", "st_l3_l_m2_d3",
        ],
    },
    {
        key: "est_l5_ancho",
        label: "Estabilidad % Ancho - 5to Lavado",
        speak: "Estabilidad quinto lavado, porcentaje ancho. Dicte tres datos de muestra 1 y tres datos de muestra 2.",
        fields: [
            "st_l5_a_m1_d1", "st_l5_a_m1_d2", "st_l5_a_m1_d3",
            "st_l5_a_m2_d1", "st_l5_a_m2_d2", "st_l5_a_m2_d3",
        ],
    },
    {
        key: "est_l5_largo",
        label: "Estabilidad % Largo - 5to Lavado",
        speak: "Estabilidad quinto lavado, porcentaje largo. Dicte tres datos de muestra 1 y tres datos de muestra 2.",
        fields: [
            "st_l5_l_m1_d1", "st_l5_l_m1_d2", "st_l5_l_m1_d3",
            "st_l5_l_m2_d1", "st_l5_l_m2_d2", "st_l5_l_m2_d3",
        ],
    },
    {
        key: "revirado_l1",
        label: "Revirado - 1er Lavado (M1/M2)",
        speak: "Revirado primer lavado. Dicte AC y BD de muestra 1, luego AC y BD de muestra 2.",
        fields: ["rv1_m1_ac", "rv1_m1_bd", "rv1_m2_ac", "rv1_m2_bd"],
    },
    {
        key: "revirado_ln",
        label: "Revirado - Lavado N (M1/M2)",
        speak: "Revirado lavado N. Primero diga el numero de lavado, luego AC y BD de muestra 1 y AC y BD de muestra 2.",
        fields: ["rvn_n", "rvn_m1_ac", "rvn_m1_bd", "rvn_m2_ac", "rvn_m2_bd"],
    },
    {
        key: "densidad",
        label: "Densidad",
        speak: "Densidad. Dicte tres mediciones.",
        fields: ["den_1", "den_2", "den_3"],
    },
    {
        key: "ancho",
        label: "Ancho",
        speak: "Ancho. Dicte tres mediciones.",
        fields: ["anc_1", "anc_2", "anc_3"],
    },
];

const FIELD_LABEL = {
    st_l1_a_m1_d1: "% Ancho M1 - 1er Lavado D1",
    st_l1_a_m1_d2: "% Ancho M1 - 1er Lavado D2",
    st_l1_a_m1_d3: "% Ancho M1 - 1er Lavado D3",
    st_l1_a_m2_d1: "% Ancho M2 - 1er Lavado D1",
    st_l1_a_m2_d2: "% Ancho M2 - 1er Lavado D2",
    st_l1_a_m2_d3: "% Ancho M2 - 1er Lavado D3",
    st_l1_l_m1_d1: "% Largo M1 - 1er Lavado D1",
    st_l1_l_m1_d2: "% Largo M1 - 1er Lavado D2",
    st_l1_l_m1_d3: "% Largo M1 - 1er Lavado D3",
    st_l1_l_m2_d1: "% Largo M2 - 1er Lavado D1",
    st_l1_l_m2_d2: "% Largo M2 - 1er Lavado D2",
    st_l1_l_m2_d3: "% Largo M2 - 1er Lavado D3",

    st_l3_a_m1_d1: "% Ancho M1 - 3er Lavado D1",
    st_l3_a_m1_d2: "% Ancho M1 - 3er Lavado D2",
    st_l3_a_m1_d3: "% Ancho M1 - 3er Lavado D3",
    st_l3_a_m2_d1: "% Ancho M2 - 3er Lavado D1",
    st_l3_a_m2_d2: "% Ancho M2 - 3er Lavado D2",
    st_l3_a_m2_d3: "% Ancho M2 - 3er Lavado D3",
    st_l3_l_m1_d1: "% Largo M1 - 3er Lavado D1",
    st_l3_l_m1_d2: "% Largo M1 - 3er Lavado D2",
    st_l3_l_m1_d3: "% Largo M1 - 3er Lavado D3",
    st_l3_l_m2_d1: "% Largo M2 - 3er Lavado D1",
    st_l3_l_m2_d2: "% Largo M2 - 3er Lavado D2",
    st_l3_l_m2_d3: "% Largo M2 - 3er Lavado D3",

    st_l5_a_m1_d1: "% Ancho M1 - 5to Lavado D1",
    st_l5_a_m1_d2: "% Ancho M1 - 5to Lavado D2",
    st_l5_a_m1_d3: "% Ancho M1 - 5to Lavado D3",
    st_l5_a_m2_d1: "% Ancho M2 - 5to Lavado D1",
    st_l5_a_m2_d2: "% Ancho M2 - 5to Lavado D2",
    st_l5_a_m2_d3: "% Ancho M2 - 5to Lavado D3",
    st_l5_l_m1_d1: "% Largo M1 - 5to Lavado D1",
    st_l5_l_m1_d2: "% Largo M1 - 5to Lavado D2",
    st_l5_l_m1_d3: "% Largo M1 - 5to Lavado D3",
    st_l5_l_m2_d1: "% Largo M2 - 5to Lavado D1",
    st_l5_l_m2_d2: "% Largo M2 - 5to Lavado D2",
    st_l5_l_m2_d3: "% Largo M2 - 5to Lavado D3",

    rv1_m1_ac: "Revirado M1 AC",
    rv1_m1_bd: "Revirado M1 BD",
    rv1_m2_ac: "Revirado M2 AC",
    rv1_m2_bd: "Revirado M2 BD",
    rvn_n: "Lavado N",
    rvn_m1_ac: "Revirado N M1 AC",
    rvn_m1_bd: "Revirado N M1 BD",
    rvn_m2_ac: "Revirado N M2 AC",
    rvn_m2_bd: "Revirado N M2 BD",
    den_1: "Densidad 1",
    den_2: "Densidad 2",
    den_3: "Densidad 3",
    anc_1: "Ancho 1",
    anc_2: "Ancho 2",
    anc_3: "Ancho 3",
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

function extractSpeechFloats(rawText) {
    const text = _normalizeSpokenNumberText(rawText);
    const matches = text.match(/-?\d+(?:[\.,]\d+)?/g) || [];
    return matches.map((m) => Number(m.replace(",", "."))).filter((n) => Number.isFinite(n));
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

    // Convert common spoken numbers to digits first.
    text = text.replace(/\b([a-z]+)\b/g, (word) => unitMap[word] ?? word);

    // Handle compound tens such as "30 y 5".
    text = text.replace(/\b(\d{2})\s+y\s+(\d)\b/g, (_, tens, units) => String(Number(tens) + Number(units)));

    // Normalize spoken decimal separators with optional spaces: "12 coma 5" => "12.5".
    text = text
        .replace(/(-?\d+)\s*(?:coma|punto)\s*(\d+)/g, "$1.$2")
        .replace(/coma|punto/g, ".")
        .replace(/\s*\.\s*/g, ".");

    // Normalize spoken negatives, including decimals: "menos cinco punto cinco" => "-5.5".
    text = text
        .replace(/\b(?:menos|negativo)\s+(\d+)\.(\d+)\b/g, "-$1.$2")
        .replace(/\b(?:menos|negativo)\s+(\d+(?:\.\d+)?)\b/g, "-$1");

    return text;
}

function getInitialValues() {
    const vals = {};
    for (const step of STEPS) {
        for (const fieldName of step.fields) {
            vals[fieldName] = "";
        }
    }
    return vals;
}

function avg3(v1, v2, v3) {
    return (asFloat(v1) + asFloat(v2) + asFloat(v3)) / 3;
}

function washAvg(values, washCode, type) {
    const axis = type === "ancho" ? "a" : "l";
    const m1 = avg3(
        values[`st_${washCode}_${axis}_m1_d1`],
        values[`st_${washCode}_${axis}_m1_d2`],
        values[`st_${washCode}_${axis}_m1_d3`]
    );
    const m2 = avg3(
        values[`st_${washCode}_${axis}_m2_d1`],
        values[`st_${washCode}_${axis}_m2_d2`],
        values[`st_${washCode}_${axis}_m2_d3`]
    );
    return (m1 + m2) / 2;
}

export class QualityDimrevScreen extends Component {
    static props = {
        action: { type: Object, optional: true },
        actionId: { type: Number, optional: true },
        className: { type: String, optional: true },
        updateActionState: { type: Function, optional: true },
        "*": true,
    };

    setup() {
        this.STEPS = STEPS;
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.homeMenu = useService("home_menu");

        this._speechRecognition = null;
        this._voiceAudioCtx = null;
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
            voiceSupported: false,
            voiceActive: false,
            voiceShouldStayOn: false,
            voiceError: "",
            voiceTranscript: "",
            currentStep: 0,
            bufferedNumbers: [],
            pendingNumbers: [],
            awaitingOk: false,
            evalId: 0,
            inEvaluation: false,
            stabilityDone: {
                l1_ancho_done: false,
                l1_largo_done: false,
                l1_done: false,
                l3_ancho_done: false,
                l3_largo_done: false,
                l3_done: false,
                l5_ancho_done: false,
                l5_largo_done: false,
                l5_done: false,
            },
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
            if (this._voiceAudioCtx) {
                try {
                    this._voiceAudioCtx.close();
                } catch {
                    // ignore
                }
            }
            this._saveDraft();
        });
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

    get activeStep() {
        return STEPS[this.state.currentStep] || STEPS[0];
    }

    get canSaveCurrentStep() {
        if (!this.state.selectedPartidaId || this.state.submitting) return false;
        const k = this.activeStep.key;
        if (k === "est_l1_largo" && !this.state.stabilityDone.l1_ancho_done) return false;
        if (k === "est_l3_ancho" && !this.state.stabilityDone.l1_done) return false;
        if (k === "est_l3_largo" && !this.state.stabilityDone.l3_ancho_done) return false;
        if (k === "est_l5_ancho" && !this.state.stabilityDone.l3_done) return false;
        if (k === "est_l5_largo" && !this.state.stabilityDone.l5_ancho_done) return false;
        return true;
    }

    get estAnchoAvgL1() {
        return washAvg(this.state.values, "l1", "ancho");
    }

    get estAnchoAvgL3() {
        return washAvg(this.state.values, "l3", "ancho");
    }

    get estAnchoAvgL5() {
        return washAvg(this.state.values, "l5", "ancho");
    }

    get estLargoAvgL1() {
        return washAvg(this.state.values, "l1", "largo");
    }

    get estLargoAvgL3() {
        return washAvg(this.state.values, "l3", "largo");
    }

    get estLargoAvgL5() {
        return washAvg(this.state.values, "l5", "largo");
    }

    get reviradoM1() {
        const ac = asFloat(this.state.values.rv1_m1_ac);
        const bd = asFloat(this.state.values.rv1_m1_bd);
        return ac + bd ? ((ac - bd) / (ac + bd)) * 200 : 0;
    }

    get reviradoM2() {
        const ac = asFloat(this.state.values.rv1_m2_ac);
        const bd = asFloat(this.state.values.rv1_m2_bd);
        return ac + bd ? ((ac - bd) / (ac + bd)) * 200 : 0;
    }

    get reviradoPromedio() {
        return (this.reviradoM1 + this.reviradoM2) / 2;
    }

    get reviradoNLavado() {
        return Math.trunc(asFloat(this.state.values.rvn_n));
    }

    get reviradoNM1() {
        const ac = asFloat(this.state.values.rvn_m1_ac);
        const bd = asFloat(this.state.values.rvn_m1_bd);
        return ac + bd ? ((ac - bd) / (ac + bd)) * 200 : 0;
    }

    get reviradoNM2() {
        const ac = asFloat(this.state.values.rvn_m2_ac);
        const bd = asFloat(this.state.values.rvn_m2_bd);
        return ac + bd ? ((ac - bd) / (ac + bd)) * 200 : 0;
    }

    get reviradoNPromedio() {
        return (this.reviradoNM1 + this.reviradoNM2) / 2;
    }

    get densidadPromedio() {
        return (asFloat(this.state.values.den_1) + asFloat(this.state.values.den_2) + asFloat(this.state.values.den_3)) / 3;
    }

    get anchoPromedio() {
        return (asFloat(this.state.values.anc_1) + asFloat(this.state.values.anc_2) + asFloat(this.state.values.anc_3)) / 3;
    }

    getStepFieldLabel(fieldName) {
        return FIELD_LABEL[fieldName] || fieldName;
    }

    onFieldChange(fieldName, ev) {
        this.state.values[fieldName] = (ev.target.value || "").replace(",", ".");
        this._saveDraft();
    }

    _defaultStabilityState() {
        return {
            l1_ancho_done: false,
            l1_largo_done: false,
            l1_done: false,
            l3_ancho_done: false,
            l3_largo_done: false,
            l3_done: false,
            l5_ancho_done: false,
            l5_largo_done: false,
            l5_done: false,
        };
    }

    _saveDraft() {
        const draft = {
            partidaQuery: this.state.partidaQuery,
            selectedPartidaId: this.state.selectedPartidaId,
            values: this.state.values,
            currentStep: this.state.currentStep,
            awaitingOk: this.state.awaitingOk,
            pendingNumbers: this.state.pendingNumbers,
            bufferedNumbers: this.state.bufferedNumbers,
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
            this.state.awaitingOk = Boolean(draft.awaitingOk);
            this.state.pendingNumbers = Array.isArray(draft.pendingNumbers) ? draft.pendingNumbers : [];
            this.state.bufferedNumbers = Array.isArray(draft.bufferedNumbers) ? draft.bufferedNumbers : [];
        } catch {
            // ignore
        }
    }

    async loadPartidas(query = "") {
        this.state.loading = true;
        this.state.error = "";
        try {
            this.state.partidas = await this.orm.call("control.estabilidad.revirado.eval", "action_tablet_get_partidas", [query, 100]);
            this._syncSelectedPartidaData();
        } catch (error) {
            this.state.error = error.message || "No se pudieron cargar las partidas.";
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
        this.state.selectedPartidaData = found || null;
        if (found?.batch) this.state.partidaQuery = found.batch;
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

    async startEvaluation() {
        if (!this.state.selectedPartidaId || this.state.submitting) {
            return;
        }
        this.state.inEvaluation = true;
        await this._loadPartidaEvaluation();
    }

    clearPartida() {
        this.state.selectedPartidaId = "";
        this.state.selectedPartidaData = null;
        this.state.partidaQuery = "";
        this.state.values = getInitialValues();
        this.state.evalId = 0;
        this.state.inEvaluation = false;
        this.state.stabilityDone = this._defaultStabilityState();
        this._saveDraft();
    }

    async _loadPartidaEvaluation() {
        if (!this.state.selectedPartidaId) return;
        try {
            const payload = await this.orm.call("control.estabilidad.revirado.eval", "action_tablet_get_or_create", [
                Number(this.state.selectedPartidaId),
            ]);
            this.state.evalId = Number(payload?.id || 0);
            this.state.values = { ...getInitialValues(), ...(payload?.values || {}) };
            this.state.stabilityDone = payload?.stability || this._defaultStabilityState();
            this._setStepFromProgress();
        } catch (error) {
            this.state.error = error.message || "No se pudo cargar la evaluación de la partida.";
        }
    }

    _setStepFromProgress() {
        if (!this.state.stabilityDone.l1_ancho_done) {
            this.state.currentStep = 0;
            return;
        }
        if (!this.state.stabilityDone.l1_largo_done) {
            this.state.currentStep = 1;
            return;
        }
        if (!this.state.stabilityDone.l3_ancho_done) {
            this.state.currentStep = 2;
            return;
        }
        if (!this.state.stabilityDone.l3_largo_done) {
            this.state.currentStep = 3;
            return;
        }
        if (!this.state.stabilityDone.l5_ancho_done) {
            this.state.currentStep = 4;
            return;
        }
        if (!this.state.stabilityDone.l5_largo_done) {
            this.state.currentStep = 5;
            return;
        }
    }

    _canGoToStepByKey(key) {
        if (key === "est_l1_ancho") return true;
        if (key === "est_l1_largo") return this.state.stabilityDone.l1_ancho_done;
        if (key === "est_l3_ancho") return this.state.stabilityDone.l1_done;
        if (key === "est_l3_largo") return this.state.stabilityDone.l3_ancho_done;
        if (key === "est_l5_ancho") return this.state.stabilityDone.l3_done;
        if (key === "est_l5_largo") return this.state.stabilityDone.l5_ancho_done;
        return true;
    }

    goToStep(index) {
        const target = Math.max(0, Math.min(index, STEPS.length - 1));
        const key = STEPS[target]?.key;
        if (!this._canGoToStepByKey(key)) {
            this.notification.add("Este paso aun no esta habilitado para la partida.", { type: "warning" });
            return;
        }
        this.state.currentStep = target;
        this.state.bufferedNumbers = [];
        this.state.pendingNumbers = [];
        this.state.awaitingOk = false;
        this._saveDraft();
    }

    async nextStep() {
        const saved = await this._autoSaveCurrentStepIfNeeded();
        if (!saved) return;
        if (this.state.currentStep < STEPS.length - 1) this.goToStep(this.state.currentStep + 1);
    }

    async previousStep() {
        const saved = await this._autoSaveCurrentStepIfNeeded();
        if (!saved) return;
        if (this.state.currentStep > 0) this.goToStep(this.state.currentStep - 1);
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
            void this._processVoiceCommand(finalText);
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

        await this._ensureMicrophonePermission();

        this.state.voiceError = "";
        this.state.voiceShouldStayOn = true;
        this._ensureVoiceAudioContext();
        try {
            this._speechRecognition.start();
            this.state.voiceActive = true;
        } catch (error) {
            this.state.voiceShouldStayOn = false;
            this.state.voiceActive = false;
            this.state.voiceError = `No se pudo iniciar el dictado: ${error?.message || "error desconocido"}`;
            this.notification.add(this.state.voiceError, { type: "danger" });
            return;
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
            } catch (error) {
                this.state.voiceActive = false;
                this.state.voiceError = `No se pudo reactivar el dictado: ${error?.message || "error desconocido"}`;
            }
        }, 350);
    }

    async _ensureMicrophonePermission() {
        if (!navigator.mediaDevices?.getUserMedia) {
            return true;
        }
        let stream = null;
        try {
            stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            return true;
        } catch {
            this.state.voiceError = "Permiso de microfono denegado o dispositivo no disponible.";
            this.notification.add(`${this.state.voiceError} Se intentara iniciar el dictado de todas formas.`, {
                type: "warning",
            });
            return false;
        } finally {
            for (const track of stream?.getTracks() || []) {
                track.stop();
            }
        }
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

    async _processVoiceCommand(rawText) {
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
            await this.nextStep();
            this._saveDraft();
            return;
        }

        if (/\banterior\b/.test(text)) {
            await this.previousStep();
            this._saveDraft();
            return;
        }

        if (this._processJumpCommand(text)) return;

        const numbers = extractSpeechFloats(rawText);
        if (!numbers.length) {
            this.state.voiceError = "No se detectaron numeros en el dictado.";
            return;
        }

        const assigned = this._assignNumbersToNextFields(numbers);
        if (!assigned) {
            this.state.voiceError = "Este paso ya esta completo. Diga limpiar para corregir o siguiente para avanzar.";
            return;
        }

        this.state.voiceError = "";
        const needed = this.activeStep.fields.length;
        const filled = this._countFilledActiveFields();
        this.state.voiceTranscript = `${rawText} [+${assigned}] [${filled}/${needed}]`;
        this._playCue("ok");
        this._saveDraft();
    }

    _assignNumbersToNextFields(numbers) {
        const fields = this.activeStep.fields || [];
        let assigned = 0;
        for (const value of numbers) {
            const idx = fields.findIndex((fieldName) => `${this.state.values[fieldName] || ""}`.trim() === "");
            if (idx === -1) {
                break;
            }
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
                this._playCue("error");
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
        this.state.bufferedNumbers = [];
        this.state.pendingNumbers = [];
        this.state.awaitingOk = false;
        this._playCue("error");
    }

    _countFilledActiveFields() {
        const fields = this.activeStep.fields || [];
        return fields.filter((fieldName) => `${this.state.values[fieldName] || ""}`.trim() !== "").length;
    }

    _processJumpCommand(text) {
        const jumpMap = [
            { re: /estabilidad.*ancho.*(1er|primer).*(lavado)/, idx: 0 },
            { re: /estabilidad.*largo.*(1er|primer).*(lavado)/, idx: 1 },
            { re: /estabilidad.*ancho.*(3er|tercer).*(lavado)/, idx: 2 },
            { re: /estabilidad.*largo.*(3er|tercer).*(lavado)/, idx: 3 },
            { re: /estabilidad.*ancho.*(5to|quinto).*(lavado)/, idx: 4 },
            { re: /estabilidad.*largo.*(5to|quinto).*(lavado)/, idx: 5 },
            { re: /revirado.*(1er|primer).*(lavado)/, idx: 6 },
            { re: /revirado.*lavado\s*n|revirado.*(3er|4to|5to|tercer|cuarto|quinto).*(lavado)/, idx: 7 },
            { re: /densidad/, idx: 8 },
            { re: /\bancho\b/, idx: 9 },
        ];
        for (const item of jumpMap) {
            if (item.re.test(text)) {
                this.goToStep(item.idx);
                return true;
            }
        }
        return false;
    }

    confirmPending() {
        if (!this.state.awaitingOk || !this.state.pendingNumbers.length) return;
        this.activeStep.fields.forEach((fieldName, idx) => {
            this.state.values[fieldName] = this.state.pendingNumbers[idx] ?? "";
        });
        this.state.awaitingOk = false;
        this.state.bufferedNumbers = [];
        this.state.pendingNumbers = [];
        this._playCue("ok");

        if (this.activeStep.key.startsWith("est_")) {
            this._speak("Datos confirmados. Presione guardar paso para registrar este bloque.");
        } else if (this.state.currentStep < STEPS.length - 1) {
            this.nextStep();
        } else {
            this._speak("Todos los datos fueron capturados. Puede guardar la evaluación.");
        }
        this._saveDraft();
    }

    rejectPending() {
        this.state.awaitingOk = false;
        this.state.bufferedNumbers = [];
        this.state.pendingNumbers = [];
        this._playCue("error");
        this._announceCurrentStep();
        this._saveDraft();
    }

    _announceCurrentStep() {
        // Intentionally silent: operator requested no spoken prompts during dictation.
    }

    _speak(text) {
        // Intentionally silent: operator requested no spoken prompts during dictation.
        void text;
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

    _playCue(type) {
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
        const tone = (freq, start, duration, gain = 0.04, wave = "sine") => {
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
            tone(1100, now, 0.06, 0.04, "triangle");
            tone(1500, now + 0.08, 0.08, 0.04, "triangle");
            return;
        }
        tone(260, now, 0.16, 0.05, "square");
        tone(190, now + 0.19, 0.2, 0.05, "square");
    }

    async onSave() {
        if (!this.state.selectedPartidaId) {
            this.notification.add("Seleccione una partida.", { type: "warning" });
            return;
        }
        if (!this.canSaveCurrentStep) {
            this.notification.add("Este paso aun no esta habilitado para la partida.", { type: "warning" });
            return;
        }

        this.state.submitting = true;
        this.state.error = "";
        try {
            const step = this.activeStep;
            const payload = {};
            for (const fname of step.fields) payload[fname] = asFloat(this.state.values[fname]);

            const result = await this.orm.call("control.estabilidad.revirado.eval", "action_tablet_submit_step", [
                Number(this.state.selectedPartidaId),
                step.key,
                payload,
            ]);
            this.state.stabilityDone = result?.stability || this.state.stabilityDone;
            this.notification.add(`Paso guardado en ${result?.name || "evaluacion"}.`, { type: "success" });

            this.state.awaitingOk = false;
            this.state.bufferedNumbers = [];
            this.state.pendingNumbers = [];
            if (this.state.currentStep < STEPS.length - 1) await this.nextStep();
            this._saveDraft();
        } catch (error) {
            this.state.error = error.message || "No se pudo guardar la evaluación.";
        } finally {
            this.state.submitting = false;
        }
    }

    async _autoSaveCurrentStepIfNeeded() {
        if (!this.state.selectedPartidaId || this.state.submitting) {
            return false;
        }
        if (!this.canSaveCurrentStep) {
            return true;
        }
        if (!this._countFilledActiveFields()) {
            return true;
        }

        this.state.submitting = true;
        this.state.error = "";
        try {
            const step = this.activeStep;
            const payload = {};
            for (const fname of step.fields) {
                payload[fname] = asFloat(this.state.values[fname]);
            }

            const result = await this.orm.call("control.estabilidad.revirado.eval", "action_tablet_submit_step", [
                Number(this.state.selectedPartidaId),
                step.key,
                payload,
            ]);

            this.state.stabilityDone = result?.stability || this.state.stabilityDone;
            this.state.awaitingOk = false;
            this.state.bufferedNumbers = [];
            this.state.pendingNumbers = [];
            return true;
        } catch (error) {
            this.state.error = error.message || "No se pudo guardar automaticamente el paso.";
            this.notification.add(this.state.error, { type: "danger" });
            return false;
        } finally {
            this.state.submitting = false;
        }
    }

    async onBackToSearch() {
        if (this.state.inEvaluation) {
            const saved = await this._autoSaveCurrentStepIfNeeded();
            if (!saved) return;
        }

        this._stopVoiceRecognition();
        this.clearPartida();
        this.state.error = "";
        this.state.showPartidaDropdown = false;
        this.state.inEvaluation = false;
        this._saveDraft();
    }

    async close() {
        if (this.state.inEvaluation) {
            const saved = await this._autoSaveCurrentStepIfNeeded();
            if (!saved) return;
        }
        this._stopVoiceRecognition();
        this._saveDraft();
        if (window.history.length > 1) {
            window.history.back();
            return;
        }
        await this.homeMenu.toggle();
    }
}

QualityDimrevScreen.template = "idtx_batch_quality.QualityDimrevScreen";
registry.category("actions").add("idtx_quality.dimrev_screen", QualityDimrevScreen);
