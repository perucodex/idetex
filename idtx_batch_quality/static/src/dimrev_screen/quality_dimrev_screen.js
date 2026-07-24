/** @odoo-module */

import { Component, onMounted, onWillStart, onWillUnmount, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

const DRAFT_STORAGE_KEY = "idtx_batch_quality.dimrev_screen.draft.v2";

const STEPS = [
    {
        key: "est_l1_m1",
        label: "1er Lavado - Muestra 1",
        speak: "Primer lavado muestra 1. Dicte porcentaje ancho, porcentaje largo, AC y BD.",
        fields: [
            "st_l1_a_m1_d1", "st_l1_a_m1_d2", "st_l1_a_m1_d3",
            "st_l1_l_m1_d1", "st_l1_l_m1_d2", "st_l1_l_m1_d3",
            "rv1_m1_ac", "rv1_m1_bd",
        ],
    },
    {
        key: "est_l1_m2",
        label: "1er Lavado - Muestra 2",
        speak: "Primer lavado muestra 2. Dicte porcentaje ancho, porcentaje largo, AC y BD.",
        fields: [
            "st_l1_a_m2_d1", "st_l1_a_m2_d2", "st_l1_a_m2_d3",
            "st_l1_l_m2_d1", "st_l1_l_m2_d2", "st_l1_l_m2_d3",
            "rv1_m2_ac", "rv1_m2_bd",
        ],
    },
    {
        key: "est_l3_m1",
        label: "3er Lavado - Muestra 1",
        speak: "Tercer lavado muestra 1. Dicte porcentaje ancho, porcentaje largo, AC y BD.",
        fields: [
            "st_l3_a_m1_d1", "st_l3_a_m1_d2", "st_l3_a_m1_d3",
            "st_l3_l_m1_d1", "st_l3_l_m1_d2", "st_l3_l_m1_d3",
            "rv3_m1_ac", "rv3_m1_bd",
        ],
    },
    {
        key: "est_l3_m2",
        label: "3er Lavado - Muestra 2",
        speak: "Tercer lavado muestra 2. Dicte porcentaje ancho, porcentaje largo, AC y BD.",
        fields: [
            "st_l3_a_m2_d1", "st_l3_a_m2_d2", "st_l3_a_m2_d3",
            "st_l3_l_m2_d1", "st_l3_l_m2_d2", "st_l3_l_m2_d3",
            "rv3_m2_ac", "rv3_m2_bd",
        ],
    },
    {
        key: "est_l5_m1",
        label: "5to Lavado - Muestra 1",
        speak: "Quinto lavado muestra 1. Dicte porcentaje ancho, porcentaje largo, AC y BD.",
        fields: [
            "st_l5_a_m1_d1", "st_l5_a_m1_d2", "st_l5_a_m1_d3",
            "st_l5_l_m1_d1", "st_l5_l_m1_d2", "st_l5_l_m1_d3",
            "rv5_m1_ac", "rv5_m1_bd",
        ],
    },
    {
        key: "est_l5_m2",
        label: "5to Lavado - Muestra 2",
        speak: "Quinto lavado muestra 2. Dicte porcentaje ancho, porcentaje largo, AC y BD.",
        fields: [
            "st_l5_a_m2_d1", "st_l5_a_m2_d2", "st_l5_a_m2_d3",
            "st_l5_l_m2_d1", "st_l5_l_m2_d2", "st_l5_l_m2_d3",
            "rv5_m2_ac", "rv5_m2_bd",
        ],
    },
    {
        key: "est_ln_m1",
        label: "Lavado N - Muestra 1",
        speak: "Lavado N muestra 1. Dicte porcentaje ancho, porcentaje largo, AC y BD.",
        fields: [
            "rvn_n",
            "st_ln_a_m1_d1", "st_ln_a_m1_d2", "st_ln_a_m1_d3",
            "st_ln_l_m1_d1", "st_ln_l_m1_d2", "st_ln_l_m1_d3",
            "rvn_m1_ac", "rvn_m1_bd",
        ],
    },
    {
        key: "est_ln_m2",
        label: "Lavado N - Muestra 2",
        speak: "Lavado N muestra 2. Dicte porcentaje ancho, porcentaje largo, AC y BD.",
        fields: [
            "st_ln_a_m2_d1", "st_ln_a_m2_d2", "st_ln_a_m2_d3",
            "st_ln_l_m2_d1", "st_ln_l_m2_d2", "st_ln_l_m2_d3",
            "rvn_m2_ac", "rvn_m2_bd",
        ],
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
    {
        key: "inclinacion",
        label: "Inclinacion",
        speak: "Inclinacion. Dicte antes de lavar.",
        fields: ["tilt_before_m1", "tilt_before_m2"],
    },
    {
        key: "inclinacion_after",
        label: "Inclinacion Despues de Lavar",
        speak: "Inclinacion despues de lavar. Dicte el valor.",
        fields: ["tilt_after_m1", "tilt_after_m2"],
    },
];

const MODE_STEP_KEYS = {
    l1: ["ancho", "densidad", "inclinacion", "est_l1_m1", "est_l1_m2", "inclinacion_after"],
    l3: ["est_l3_m1", "est_l3_m2", "inclinacion_after"],
    l5: ["est_l5_m1", "est_l5_m2", "inclinacion_after"],
    ln: ["est_ln_m1", "est_ln_m2", "inclinacion_after"],
};

const SAMPLE_TYPE_OPTIONS = [
    { value: "", label: "Seleccione..." },
    { value: "seco_ppe", label: "Seco PPE" },
    { value: "empastado_digital", label: "Empastado Digital" },
    { value: "seco_estampado_rama", label: "Seco Estampado Rama" },
    { value: "acabado", label: "Acabado" },
    { value: "sanforizado_compactado", label: "Sanforizado y Compactado" },
    { value: "estampado", label: "Estampado" },
];

const STEP_INDEX_BY_KEY = Object.fromEntries(STEPS.map((step, idx) => [step.key, idx]));

const STEP_GROUPS = [
    {
        title: "1er Lavado",
        options: [
            { key: "est_l1_m1", label: "Muestra 1" },
            { key: "est_l1_m2", label: "Muestra 2" },
        ],
    },
    {
        title: "3er Lavado",
        options: [
            { key: "est_l3_m1", label: "Muestra 1" },
            { key: "est_l3_m2", label: "Muestra 2" },
        ],
    },
    {
        title: "5to Lavado",
        options: [
            { key: "est_l5_m1", label: "Muestra 1" },
            { key: "est_l5_m2", label: "Muestra 2" },
        ],
    },
    {
        title: "Revirado",
        options: [
            { key: "revirado_ln_m1", label: "Muestra 1" },
            { key: "revirado_ln_m2", label: "Muestra 2" },
        ],
    },
    {
        title: "Densidad y Ancho",
        options: [
            { key: "ancho", label: "Ancho" },
            { key: "densidad", label: "Densidad" },
        ],
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

    st_ln_a_m1_d1: "% Ancho M1 - Lavado N D1",
    st_ln_a_m1_d2: "% Ancho M1 - Lavado N D2",
    st_ln_a_m1_d3: "% Ancho M1 - Lavado N D3",
    st_ln_a_m2_d1: "% Ancho M2 - Lavado N D1",
    st_ln_a_m2_d2: "% Ancho M2 - Lavado N D2",
    st_ln_a_m2_d3: "% Ancho M2 - Lavado N D3",
    st_ln_l_m1_d1: "% Largo M1 - Lavado N D1",
    st_ln_l_m1_d2: "% Largo M1 - Lavado N D2",
    st_ln_l_m1_d3: "% Largo M1 - Lavado N D3",
    st_ln_l_m2_d1: "% Largo M2 - Lavado N D1",
    st_ln_l_m2_d2: "% Largo M2 - Lavado N D2",
    st_ln_l_m2_d3: "% Largo M2 - Lavado N D3",

    rv1_m1_ac: "Revirado M1 AC",
    rv1_m1_bd: "Revirado M1 BD",
    rv1_m2_ac: "Revirado M2 AC",
    rv1_m2_bd: "Revirado M2 BD",
    rv3_m1_ac: "Revirado 3er M1 AC",
    rv3_m1_bd: "Revirado 3er M1 BD",
    rv3_m2_ac: "Revirado 3er M2 AC",
    rv3_m2_bd: "Revirado 3er M2 BD",
    rv5_m1_ac: "Revirado 5to M1 AC",
    rv5_m1_bd: "Revirado 5to M1 BD",
    rv5_m2_ac: "Revirado 5to M2 AC",
    rv5_m2_bd: "Revirado 5to M2 BD",
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
    tilt_before_m1: "Inclinacion Antes de Lavar M1",
    tilt_before_m2: "Inclinacion Antes de Lavar M2",
    tilt_after_m1: "Inclinacion Despues de Lavar M1",
    tilt_after_m2: "Inclinacion Despues de Lavar M2",
};

const TILT_DIRECTION_FIELD_BY_VALUE_FIELD = {
    tilt_before_m1: "tilt_before_dir_m1",
    tilt_before_m2: "tilt_before_dir_m2",
    tilt_after_m1: "tilt_after_dir_m1",
    tilt_after_m2: "tilt_after_dir_m2",
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

function extractSpeechFloats(rawText) {
    const text = _normalizeSpokenNumberText(rawText);
    const matches = text.match(/-?\d+(?:[\.,]\d+)?/g) || [];
    return matches.map((m) => Number(m.replace(",", "."))).filter((n) => Number.isFinite(n));
}

function extractTiltEntries(rawText) {
    const text = normalizeSpeechText(rawText);
    const entries = [];
    const regex = /(-?\d+(?:[\.,]\d+)?)(?:\s*(z|s))?/gi;
    let match;
    while ((match = regex.exec(text))) {
        const value = Number((match[1] || "").replace(",", "."));
        if (!Number.isFinite(value)) continue;
        const spokenDir = (match[2] || "").toLowerCase();
        const dir = spokenDir === "s" || value < 0 ? "s" : "z";
        entries.push({ value: Math.abs(value), dir });
    }
    return entries;
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
    vals.tilt_before_dir_m1 = "z";
    vals.tilt_before_dir_m2 = "z";
    vals.tilt_after_dir_m1 = "z";
    vals.tilt_after_dir_m2 = "z";
    return vals;
}

function avg3(v1, v2, v3) {
    return (asFloat(v1) + asFloat(v2) + asFloat(v3)) / 3;
}

function getInitialStandards() {
    return {
        density_standard: 0,
        width_standard: 0,
        tilt_standard: 0,
        width_shrinkage_from: 0,
        width_shrinkage_to: 0,
        length_shrinkage_from: 0,
        length_shrinkage_to: 0,
        twist_limit: 0,
        tilt_wash_tolerance: 0,
        density_tolerance: 0,
        width_tolerance: 0,
        has_thresholds: false,
    };
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
        this.STEP_GROUPS = STEP_GROUPS;
        this.SAMPLE_TYPE_OPTIONS = SAMPLE_TYPE_OPTIONS;
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
            sampleType: "",
            recentDensityWidth: [],
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
            evalMode: "",
            needsModeSelection: false,
            availableModes: [],
            modeSelectionTarget: "",
            selectedLavadoN: "",
            requiresFirstWashDecision: false,
            firstWashStatus: "nodata",
            criteriaOverride: false,
            isFirstRecord: false,
            repeatKind: "original",
            pendingRepeatMode: "",
            editableFirstEval: null,
            completedWashNumbers: [],
            repeatDecision: { active: false, mode: "", washN: 0 },
            reviewing: false,
            tiltRequired: false,
            tiltStandard: 0,
            standards: getInitialStandards(),
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
        return this.activeSteps[this.state.currentStep] || this.activeSteps[0] || STEPS[0];
    }

    get activeSteps() {
        const keys = MODE_STEP_KEYS[this.state.evalMode] || [];
        return keys
            .map((k) => STEPS[STEP_INDEX_BY_KEY[k]])
            .filter((step) => step && (step.key !== "inclinacion" || this.state.tiltRequired));
    }

    get canSaveCurrentStep() {
        return Boolean(this.state.selectedPartidaId && !this.state.submitting && this.state.evalMode && !this.state.needsModeSelection);
    }

    get isLastStep() {
        return this.state.currentStep >= (this.activeSteps.length - 1);
    }

    get canShowSaveProgress() {
        if (this.state.needsModeSelection || this.state.evalMode !== "l1") {
            return false;
        }
        const stepKey = this.activeStep?.key;
        return stepKey === "inclinacion";
    }

    get canFinalizeEvaluation() {
        if (!this.canSaveCurrentStep) return false;
        const fields = this.activeSteps.flatMap((s) => s.fields || []);
        const hasAllFields = (() => {
            for (const fieldName of fields) {
                if (!this.state.tiltRequired && (fieldName === "tilt_before_m1" || fieldName === "tilt_before_m2")) {
                    continue;
                }
                if (`${this.state.values[fieldName] || ""}`.trim() === "") {
                    return false;
                }
            }
            return true;
        })();

        if (this.state.evalMode === "l1") {
            const hasDensityAndWidth = ["den_1", "den_2", "den_3", "anc_1", "anc_2", "anc_3"]
                .every((fieldName) => `${this.state.values[fieldName] || ""}`.trim() !== "");
            const hasTiltBefore = `${this.state.values.tilt_before_m1 || ""}`.trim() !== ""
                && `${this.state.values.tilt_before_m2 || ""}`.trim() !== "";
            const hasProgressMinimum = hasDensityAndWidth && (!this.state.tiltRequired || hasTiltBefore);
            return hasAllFields || hasProgressMinimum;
        }

        for (const fieldName of fields) {
            if (!this.state.tiltRequired && (fieldName === "tilt_before_m1" || fieldName === "tilt_before_m2")) {
                continue;
            }
            if (`${this.state.values[fieldName] || ""}`.trim() === "") {
                return false;
            }
        }
        if (this.state.evalMode === "ln" && asFloat(this.state.values.rvn_n) <= 1) {
            return false;
        }
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

    get estAnchoAvgLN() {
        return washAvg(this.state.values, "ln", "ancho");
    }

    get estLargoAvgLN() {
        return washAvg(this.state.values, "ln", "largo");
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

    get revirado3M1() {
        const ac = asFloat(this.state.values.rv3_m1_ac);
        const bd = asFloat(this.state.values.rv3_m1_bd);
        return ac + bd ? ((ac - bd) / (ac + bd)) * 200 : 0;
    }

    get revirado3M2() {
        const ac = asFloat(this.state.values.rv3_m2_ac);
        const bd = asFloat(this.state.values.rv3_m2_bd);
        return ac + bd ? ((ac - bd) / (ac + bd)) * 200 : 0;
    }

    get revirado3Promedio() {
        return (this.revirado3M1 + this.revirado3M2) / 2;
    }

    get revirado5M1() {
        const ac = asFloat(this.state.values.rv5_m1_ac);
        const bd = asFloat(this.state.values.rv5_m1_bd);
        return ac + bd ? ((ac - bd) / (ac + bd)) * 200 : 0;
    }

    get revirado5M2() {
        const ac = asFloat(this.state.values.rv5_m2_ac);
        const bd = asFloat(this.state.values.rv5_m2_bd);
        return ac + bd ? ((ac - bd) / (ac + bd)) * 200 : 0;
    }

    get revirado5Promedio() {
        return (this.revirado5M1 + this.revirado5M2) / 2;
    }

    get densidadPromedio() {
        return (asFloat(this.state.values.den_1) + asFloat(this.state.values.den_2) + asFloat(this.state.values.den_3)) / 3;
    }

    get anchoPromedio() {
        return (asFloat(this.state.values.anc_1) + asFloat(this.state.values.anc_2) + asFloat(this.state.values.anc_3)) / 3;
    }

    get tiltBefore() {
        return (asFloat(this.state.values.tilt_before_m1) + asFloat(this.state.values.tilt_before_m2)) / 2;
    }

    get tiltAfter() {
        return (asFloat(this.state.values.tilt_after_m1) + asFloat(this.state.values.tilt_after_m2)) / 2;
    }

    get standards() {
        return this.state.standards || getInitialStandards();
    }

    get repeatKindLabel() {
        if (this.state.repeatKind === "test") return "Test";
        if (this.state.repeatKind === "reproceso") return "Reproceso";
        return "Original";
    }

    get reviewAnchoAvg() {
        return washAvg(this.state.values, this.state.evalMode, "ancho");
    }

    get reviewLargoAvg() {
        return washAvg(this.state.values, this.state.evalMode, "largo");
    }

    get reviewReviradoProm() {
        const map = {
            l1: this.reviradoPromedio,
            l3: this.revirado3Promedio,
            l5: this.revirado5Promedio,
            ln: this.reviradoNPromedio,
        };
        return map[this.state.evalMode] || 0;
    }

    get reviewMetrics() {
        // Indicadores pass/fail (verde/rojo) para la pantalla de revision.
        // Replica el criterio del backend _compute_result_state; ok=null cuando
        // no hay estandar (se muestra en gris, dato capturado pero no validado).
        const s = this.standards;
        const has = Boolean(s.has_thresholds);
        const tolRatio = (v) => (Math.abs(v) > 1 ? Math.abs(v) / 100 : Math.abs(v));
        const metrics = [];

        const anchoAvg = this.reviewAnchoAvg;
        let anchoOk = null;
        if (has && (s.width_shrinkage_from || s.width_shrinkage_to)) {
            anchoOk = !(s.width_shrinkage_from && anchoAvg < s.width_shrinkage_from)
                && !(s.width_shrinkage_to && anchoAvg > s.width_shrinkage_to);
        }
        metrics.push({ key: "ancho_avg", label: "% Ancho Promedio", value: anchoAvg, ok: anchoOk });

        const largoAvg = this.reviewLargoAvg;
        let largoOk = null;
        if (has && (s.length_shrinkage_from || s.length_shrinkage_to)) {
            largoOk = !(s.length_shrinkage_from && largoAvg < s.length_shrinkage_from)
                && !(s.length_shrinkage_to && largoAvg > s.length_shrinkage_to);
        }
        metrics.push({ key: "largo_avg", label: "% Largo Promedio", value: largoAvg, ok: largoOk });

        const revProm = this.reviewReviradoProm;
        let revOk = null;
        if (has && s.twist_limit) {
            revOk = revProm <= s.twist_limit;
        }
        metrics.push({ key: "revirado", label: "Revirado Promedio", value: revProm, ok: revOk });

        if (this.state.evalMode === "l1") {
            const dens = this.densidadPromedio;
            let densOk = null;
            if (has && s.density_standard > 0) {
                const tol = tolRatio(s.density_tolerance);
                densOk = dens >= s.density_standard * (1 - tol) && dens <= s.density_standard * (1 + tol);
            }
            metrics.push({ key: "densidad", label: "Densidad Promedio", value: dens, ok: densOk });

            const ancho = this.anchoPromedio;
            let anchoCmOk = null;
            if (has && s.width_standard > 0) {
                anchoCmOk = ancho >= s.width_standard - s.width_tolerance && ancho <= s.width_standard + s.width_tolerance;
            }
            metrics.push({ key: "ancho_cm", label: "Ancho Promedio", value: ancho, ok: anchoCmOk });

            const tilt = this.tiltBefore;
            let tiltOk = null;
            if (has && s.tilt_standard > 0) {
                tiltOk = Math.abs(tilt - s.tilt_standard) <= s.tilt_wash_tolerance;
            }
            metrics.push({ key: "tilt", label: "Inclinacion Antes de Lavar", value: tilt, ok: tiltOk });
        }

        return metrics;
    }

    get reviewAllPass() {
        return this.reviewMetrics.every((m) => m.ok !== false);
    }

    getTiltDirection(valueFieldName) {
        const dirField = TILT_DIRECTION_FIELD_BY_VALUE_FIELD[valueFieldName];
        const raw = this.state.values[dirField];
        const dir = `${raw || "z"}`.toLowerCase();
        if (dir === "s" || Number(raw) < 0) {
            return "s";
        }
        return "z";
    }

    setTiltDirection(valueFieldName, direction) {
        const dirField = TILT_DIRECTION_FIELD_BY_VALUE_FIELD[valueFieldName];
        if (!dirField) return;
        this.state.values[dirField] = direction === "s" ? "s" : "z";
        this._saveDraft();
    }

    toggleTiltDirection(valueFieldName) {
        const current = this.getTiltDirection(valueFieldName);
        this.setTiltDirection(valueFieldName, current === "z" ? "s" : "z");
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
            sampleType: this.state.sampleType,
            evalMode: this.state.evalMode,
            needsModeSelection: this.state.needsModeSelection,
            requiresFirstWashDecision: this.state.requiresFirstWashDecision,
            criteriaOverride: this.state.criteriaOverride,
            pendingRepeatMode: this.state.pendingRepeatMode,
            repeatKind: this.state.repeatKind,
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
            this.state.sampleType = typeof draft.sampleType === "string" ? draft.sampleType : "";
            this.state.evalMode = draft.evalMode || "";
            this.state.needsModeSelection = Boolean(draft.needsModeSelection);
            this.state.requiresFirstWashDecision = Boolean(draft.requiresFirstWashDecision);
            this.state.criteriaOverride = Boolean(draft.criteriaOverride);
            this.state.pendingRepeatMode = typeof draft.pendingRepeatMode === "string" ? draft.pendingRepeatMode : "";
            this.state.repeatKind = typeof draft.repeatKind === "string" ? draft.repeatKind : "original";
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
            this.state.error = extractRpcMessage(error, "No se pudieron cargar las partidas.");
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
                this.state.sampleType = "";
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
        const previousId = this.state.selectedPartidaId;
        this.state.selectedPartidaId = String(partidaId);
        this._syncSelectedPartidaData();
        if (String(previousId || "") !== String(partidaId || "")) {
            this.state.sampleType = "";
        }
        this.state.showPartidaDropdown = false;
        this.state.inEvaluation = false;
        this._saveDraft();
    }

    async startEvaluation() {
        if (!this.state.selectedPartidaId || this.state.submitting) {
            return;
        }
        if (!this.state.sampleType) {
            this.notification.add("Seleccione el tipo de muestra antes de comenzar.", { type: "warning" });
            return;
        }
        this.state.inEvaluation = true;
        await this._loadPartidaEvaluation();
    }

    onSampleTypeChange(ev) {
        this.state.sampleType = ev.target.value || "";
        this._saveDraft();
    }

    clearPartida() {
        this.state.selectedPartidaId = "";
        this.state.selectedPartidaData = null;
        this.state.partidaQuery = "";
        this.state.sampleType = "";
        this.state.values = getInitialValues();
        this.state.evalId = 0;
        this.state.inEvaluation = false;
        this.state.evalMode = "";
        this.state.needsModeSelection = false;
        this.state.availableModes = [];
        this.state.modeSelectionTarget = "";
        this.state.selectedLavadoN = "";
        this.state.requiresFirstWashDecision = false;
        this.state.firstWashStatus = "nodata";
        this.state.criteriaOverride = false;
        this.state.isFirstRecord = false;
        this.state.tiltRequired = false;
        this.state.tiltStandard = 0;
        this.state.standards = getInitialStandards();
        this.state.recentDensityWidth = [];
        this.state.stabilityDone = this._defaultStabilityState();
        this.state.repeatKind = "original";
        this.state.pendingRepeatMode = "";
        this.state.editableFirstEval = null;
        this.state.completedWashNumbers = [];
        this.state.repeatDecision = { active: false, mode: "", washN: 0 };
        this.state.reviewing = false;
        this._saveDraft();
    }

    async _loadPartidaEvaluation() {
        if (!this.state.selectedPartidaId) return;
        try {
            const payload = await this.orm.call("control.estabilidad.revirado.eval", "action_tablet_get_eval_context", [
                Number(this.state.selectedPartidaId),
                this.state.sampleType,
            ]);
            this.state.values = getInitialValues();
            this.state.stabilityDone = this._defaultStabilityState();
            this.state.availableModes = payload?.available_modes || [];
            this.state.firstWashStatus = payload?.first_wash_status || "nodata";
            this.state.requiresFirstWashDecision = Boolean(payload?.requires_first_wash_decision);
            this.state.isFirstRecord = !Boolean(payload?.has_first_record);
            this.state.tiltRequired = Boolean(payload?.tilt_required);
            this.state.tiltStandard = asFloat(payload?.tilt_standard || 0);
            this.state.standards = { ...getInitialStandards(), ...(payload?.standards || {}) };
            this.state.recentDensityWidth = Array.isArray(payload?.recent_density_width)
                ? payload.recent_density_width
                : [];
            this.state.completedWashNumbers = Array.isArray(payload?.completed_wash_numbers)
                ? payload.completed_wash_numbers
                : [];
            this.state.editableFirstEval = payload?.editable_first_eval || null;
            this.state.repeatKind = "original";
            this.state.pendingRepeatMode = "";
            this.state.reviewing = false;
            this.state.repeatDecision = { active: false, mode: "", washN: 0 };
            const existingEval = payload?.existing_eval || null;
            if (existingEval) {
                this.state.values = { ...getInitialValues(), ...(existingEval.values || {}) };
                this.state.stabilityDone = {
                    ...this._defaultStabilityState(),
                    ...(existingEval.stability || {}),
                };
                this.state.evalId = Number(existingEval.id || 0);
                this.state.repeatKind = existingEval.repeat_kind || "original";
            }
            const requiredMode = payload?.required_mode || "";
            this.state.evalMode = requiredMode;
            this.state.needsModeSelection = !requiredMode;
            this.state.criteriaOverride = false;
            this.state.modeSelectionTarget = "";
            this.state.selectedLavadoN = "";
            this._setStepFromProgress();
        } catch (error) {
            this.state.error = extractRpcMessage(error, "No se pudo cargar la evaluación de la partida.");
        }
    }

    _enterMode(mode, repeatMode) {
        // repeatMode: "" (normal) | "reproceso" | "test" | "editar".
        // No toca state.values (el llamador decide cargar o limpiar).
        this.state.modeSelectionTarget = "";
        this.state.evalMode = mode;
        this.state.needsModeSelection = false;
        this.state.requiresFirstWashDecision = false;
        // La inclinacion antes de lavar SIEMPRE se pide en 1er lavado, sea
        // original, reproceso, test o edicion. tilt_required se recalculo al
        // cargar la partida (cuando required_mode podia no ser 'l1'), asi que
        // aqui lo derivamos del modo actual.
        this.state.tiltRequired = mode === "l1";
        this.state.repeatDecision = { active: false, mode: "", washN: 0 };
        this.state.pendingRepeatMode = repeatMode || "";
        if (repeatMode === "test") {
            this.state.repeatKind = "test";
        } else if (repeatMode === "reproceso") {
            this.state.repeatKind = "reproceso";
        } else if (repeatMode !== "editar") {
            this.state.repeatKind = "original";
        }
        this.state.currentStep = 0;
        this.state.reviewing = false;
        this.state.error = "";
        this._saveDraft();
    }

    selectEvaluationMode(mode) {
        if (this.state.requiresFirstWashDecision) return;
        if (!MODE_STEP_KEYS[mode]) return;
        if (mode === "ln") {
            this.state.modeSelectionTarget = "ln";
            this.state.selectedLavadoN = "";
            return;
        }
        const washN = mode === "l3" ? 3 : 5;
        if ((this.state.completedWashNumbers || []).includes(washN)) {
            this._openRepeatDecision(mode, washN);
            return;
        }
        this.state.values = getInitialValues();
        this._enterMode(mode, "");
    }

    _openRepeatDecision(mode, washN) {
        this.state.repeatDecision = { active: true, mode, washN };
        this.state.modeSelectionTarget = "";
        this._saveDraft();
    }

    cancelRepeatDecision() {
        this.state.repeatDecision = { active: false, mode: "", washN: 0 };
        this._saveDraft();
    }

    async chooseRepeatEdit() {
        const { mode, washN } = this.state.repeatDecision;
        let payload = null;
        if (mode === "l1") {
            payload = this.state.editableFirstEval;
        } else {
            try {
                payload = await this.orm.call("control.estabilidad.revirado.eval", "action_tablet_get_wash_payload", [
                    Number(this.state.selectedPartidaId),
                    washN,
                    this.state.sampleType,
                ]);
            } catch (error) {
                this.notification.add(extractRpcMessage(error, "No se pudo cargar el registro a editar."), { type: "warning" });
                return;
            }
        }
        if (payload && payload.values) {
            this.state.values = { ...getInitialValues(), ...(payload.values || {}) };
            this.state.repeatKind = payload.repeat_kind || "original";
        } else {
            this.state.values = getInitialValues();
        }
        if (mode === "ln") {
            this.state.values.rvn_n = `${washN}`;
        }
        this._enterMode(mode, "editar");
    }

    chooseRepeatReproceso() {
        this._startRepeat("reproceso");
    }

    chooseRepeatTest() {
        this._startRepeat("test");
    }

    _startRepeat(kind) {
        const { mode, washN } = this.state.repeatDecision;
        this.state.values = getInitialValues();
        if (mode === "ln") {
            this.state.values.rvn_n = `${washN}`;
        }
        this._enterMode(mode, kind);
    }

    chooseEditFirstWash() {
        const payload = this.state.editableFirstEval;
        if (payload && payload.values) {
            this.state.values = { ...getInitialValues(), ...(payload.values || {}) };
            this.state.repeatKind = payload.repeat_kind || "original";
        }
        this._enterMode("l1", "editar");
    }

    chooseRepeatFirstWash() {
        // Repetir el 1er lavado es una repeticion: preguntar Reproceso o Test.
        // No se limpia requiresFirstWashDecision aun; si el usuario cancela la
        // decision, vuelve a verse el panel de FAIL (_enterMode la limpia al
        // confirmar).
        this.state.criteriaOverride = false;
        this._openRepeatDecision("l1", 1);
    }

    chooseContinueByCriteria() {
        this.state.requiresFirstWashDecision = false;
        this.state.criteriaOverride = true;
        this.state.evalMode = "";
        this.state.needsModeSelection = true;
        this.state.modeSelectionTarget = "";
        this.state.selectedLavadoN = "";
        this.state.currentStep = 0;
        this.state.error = "";
        this._saveDraft();
    }

    onSelectedLavadoNInput(ev) {
        this.state.selectedLavadoN = (ev.target.value || "").replace(/[^0-9]/g, "");
        this._saveDraft();
    }

    confirmLavadoNMode() {
        const n = Math.trunc(asFloat(this.state.selectedLavadoN));
        if (n <= 1) {
            this.notification.add("El lavado N debe ser mayor a 1.", { type: "warning" });
            return;
        }
        if ((this.state.completedWashNumbers || []).includes(n)) {
            this.state.values.rvn_n = `${n}`;
            this._openRepeatDecision("ln", n);
            return;
        }
        this.state.values = getInitialValues();
        this.state.values.rvn_n = `${n}`;
        this._enterMode("ln", "");
    }

    _setStepFromProgress() {
        if (this.state.needsModeSelection || !this.state.evalMode) {
            this.state.currentStep = 0;
            return;
        }

        if (this.state.evalMode !== "l1") {
            this.state.currentStep = 0;
            return;
        }

        const hasDensityAndWidth = ["den_1", "den_2", "den_3", "anc_1", "anc_2", "anc_3"]
            .every((fieldName) => `${this.state.values[fieldName] || ""}`.trim() !== "");

        if (!hasDensityAndWidth) {
            this.state.currentStep = 0;
            return;
        }

        const stepComplete = (stepKey) => {
            const step = STEPS[STEP_INDEX_BY_KEY[stepKey]];
            const fields = step?.fields || [];
            return fields.every((fieldName) => `${this.state.values[fieldName] || ""}`.trim() !== "");
        };

        let targetKey = "est_l1_m1";
        if (this.state.tiltRequired && !stepComplete("inclinacion")) {
            targetKey = "inclinacion";
        } else if (!this.state.tiltRequired) {
            targetKey = "est_l1_m1";
        }
        if (stepComplete("est_l1_m1") && !stepComplete("est_l1_m2")) {
            targetKey = "est_l1_m2";
        } else if (stepComplete("est_l1_m1") && stepComplete("est_l1_m2") && !stepComplete("inclinacion_after")) {
            targetKey = "inclinacion_after";
        }

        const targetIdx = this.activeSteps.findIndex((step) => step.key === targetKey);
        this.state.currentStep = targetIdx >= 0 ? targetIdx : 0;
    }

    _canGoToStepByKey(key) {
        const idx = this.activeSteps.findIndex((s) => s.key === key);
        return idx >= 0;
    }

    goToStep(index) {
        const target = Math.max(0, Math.min(index, this.activeSteps.length - 1));
        const key = this.activeSteps[target]?.key;
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

    goToStepByKey(stepKey) {
        const idx = STEP_INDEX_BY_KEY[stepKey];
        if (!Number.isInteger(idx)) return;
        this.goToStep(idx);
    }

    isStepActive(stepKey) {
        return this.activeStep?.key === stepKey;
    }

    isStepEnabled(stepKey) {
        return this._canGoToStepByKey(stepKey);
    }

    async nextStep() {
        if (this.state.currentStep < this.activeSteps.length - 1) this.goToStep(this.state.currentStep + 1);
    }

    async previousStep() {
        if (this.state.reviewing) {
            this.state.reviewing = false;
            return;
        }
        if (this.state.currentStep > 0) {
            this.goToStep(this.state.currentStep - 1);
            return;
        }
        if (this.state.evalMode === "l1") {
            await this.onBackToSearch();
            return;
        }
        if (this.state.evalMode === "ln" || this.state.evalMode === "l3" || this.state.evalMode === "l5") {
            if (!this._confirmDiscardUnsaved()) {
                return;
            }
            this.state.needsModeSelection = true;
            this.state.evalMode = "";
            this.state.modeSelectionTarget = "";
            this.state.pendingRepeatMode = "";
            this.state.repeatKind = "original";
            this.state.values = getInitialValues();
            this.state.currentStep = 0;
            this._saveDraft();
            return;
        }
        if (this.state.isFirstRecord) {
            await this.onBackToSearch();
        }
    }

    _hasUnsavedData() {
        if (!this.state.inEvaluation) {
            return false;
        }
        const vals = this.state.values || {};
        return Object.keys(vals).some((key) => {
            if (key === "rvn_n" || key.endsWith("_dir_m1") || key.endsWith("_dir_m2")) {
                return false;
            }
            return `${vals[key] ?? ""}`.trim() !== "";
        });
    }

    _confirmDiscardUnsaved() {
        if (!this._hasUnsavedData()) {
            return true;
        }
        return window.confirm("Tiene datos capturados sin guardar. ¿Desea salir y perder los datos no guardados?");
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

        if (this.state.reviewing || this.state.repeatDecision.active) {
            return;
        }
        if (this.state.needsModeSelection) {
            this.state.voiceError = "Seleccione primero el lavado a evaluar.";
            return;
        }

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
        if (this.activeStep?.key === "inclinacion" || this.activeStep?.key === "inclinacion_after") {
            const tiltEntries = extractTiltEntries(rawText);
            if (!tiltEntries.length) {
                this.state.voiceError = "No se detectaron datos de inclinacion en el dictado.";
                return;
            }
            const assigned = this._assignTiltEntriesToNextFields(tiltEntries);
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
            return;
        }
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

    _assignTiltEntriesToNextFields(entries) {
        const fields = this.activeStep.fields || [];
        let assigned = 0;
        for (const entry of entries) {
            const idx = fields.findIndex((fieldName) => `${this.state.values[fieldName] || ""}`.trim() === "");
            if (idx === -1) break;
            const valueField = fields[idx];
            this.state.values[valueField] = `${entry.value}`;
            this.setTiltDirection(valueField, entry.dir);
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
            { re: /(1er|primer).*(lavado).*muestra\s*1/, key: "est_l1_m1" },
            { re: /(1er|primer).*(lavado).*muestra\s*2/, key: "est_l1_m2" },
            { re: /(3er|tercer).*(lavado).*muestra\s*1/, key: "est_l3_m1" },
            { re: /(3er|tercer).*(lavado).*muestra\s*2/, key: "est_l3_m2" },
            { re: /(5to|quinto).*(lavado).*muestra\s*1/, key: "est_l5_m1" },
            { re: /(5to|quinto).*(lavado).*muestra\s*2/, key: "est_l5_m2" },
            { re: /(lavado\s*n).*muestra\s*1/, key: "est_ln_m1" },
            { re: /(lavado\s*n).*muestra\s*2/, key: "est_ln_m2" },
            { re: /inclinacion\s+despues/, key: "inclinacion_after" },
            { re: /inclinacion\s+antes/, key: "inclinacion" },
            { re: /densidad/, key: "densidad" },
            { re: /\bancho\b/, key: "ancho" },
        ];
        for (const item of jumpMap) {
            if (item.re.test(text)) {
                const idx = this.activeSteps.findIndex((s) => s.key === item.key);
                if (idx >= 0) this.goToStep(idx);
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

    finalizeEvaluation() {
        // Antes de finalizar se muestra la pantalla de revision con los
        // indicadores pass/fail para que el usuario verifique/corrija.
        if (!this.canFinalizeEvaluation) {
            this.notification.add("Complete todos los campos antes de finalizar.", { type: "warning" });
            return;
        }
        const hasTiltAfter = `${this.state.values.tilt_after_m1 || ""}`.trim() !== ""
            && `${this.state.values.tilt_after_m2 || ""}`.trim() !== "";
        if (!hasTiltAfter) {
            this.notification.add("Ingrese la inclinacion despues de lavar antes de finalizar.", { type: "warning" });
            return;
        }
        this.state.reviewing = true;
        this._saveDraft();
    }

    backToEdit() {
        this.state.reviewing = false;
        this._saveDraft();
    }

    async confirmFinalize() {
        const payload = {};
        const fields = this.activeSteps.flatMap((s) => s.fields || []);
        for (const fname of fields) {
            const rawValue = `${this.state.values[fname] || ""}`.trim();
            if (rawValue === "") {
                continue;
            }
            payload[fname] = asFloat(rawValue);
            if (Object.prototype.hasOwnProperty.call(TILT_DIRECTION_FIELD_BY_VALUE_FIELD, fname)) {
                payload[TILT_DIRECTION_FIELD_BY_VALUE_FIELD[fname]] = this.getTiltDirection(fname);
            }
        }

        if (!Object.prototype.hasOwnProperty.call(payload, "tilt_after_m1") || !Object.prototype.hasOwnProperty.call(payload, "tilt_after_m2")) {
            this.notification.add("Ingrese la inclinacion despues de lavar antes de finalizar.", { type: "warning" });
            return;
        }

        this.state.submitting = true;
        this.state.error = "";
        try {
            const result = await this.orm.call("control.estabilidad.revirado.eval", "action_tablet_finalize", [
                Number(this.state.selectedPartidaId),
                this.state.evalMode,
                payload,
                this.state.sampleType,
                this.state.criteriaOverride,
                false,
                this.state.pendingRepeatMode || "",
            ]);
            const kindLabel = result?.repeat_kind === "test"
                ? " (Test)"
                : (result?.repeat_kind === "reproceso" ? " (Reproceso)" : "");
            if (result?.completed) {
                this.notification.add(`Evaluacion finalizada en ${result?.name || "evaluacion"}${kindLabel}.`, { type: "success" });
            } else {
                this.notification.add(`Avance guardado en ${result?.name || "evaluacion"}${kindLabel}.`, { type: "success" });
            }
            this.state.reviewing = false;
            await this.onBackToSearch(true);
        } catch (error) {
            this.state.error = extractRpcMessage(error, "No se pudo finalizar la evaluación.");
            this.notification.add(this.state.error, { type: "warning" });
        } finally {
            this.state.submitting = false;
        }
    }

    async saveProgressEvaluation() {
        if (!this.canFinalizeEvaluation) {
            this.notification.add("Para guardar avance en 1er lavado, complete ancho y densidad.", { type: "warning" });
            return;
        }

        const payload = {};
        const fields = this.activeSteps.flatMap((s) => s.fields || []);
        for (const fname of fields) {
            const rawValue = `${this.state.values[fname] || ""}`.trim();
            if (rawValue === "") {
                continue;
            }
            payload[fname] = asFloat(rawValue);
            if (Object.prototype.hasOwnProperty.call(TILT_DIRECTION_FIELD_BY_VALUE_FIELD, fname)) {
                payload[TILT_DIRECTION_FIELD_BY_VALUE_FIELD[fname]] = this.getTiltDirection(fname);
            }
        }

        this.state.submitting = true;
        this.state.error = "";
        try {
            const result = await this.orm.call("control.estabilidad.revirado.eval", "action_tablet_finalize", [
                Number(this.state.selectedPartidaId),
                this.state.evalMode,
                payload,
                this.state.sampleType,
                this.state.criteriaOverride,
                true,
                this.state.pendingRepeatMode || "",
            ]);
            this.notification.add(`Avance guardado en ${result?.name || "evaluacion"}.`, { type: "success" });
            await this.onBackToSearch(true);
        } catch (error) {
            this.state.error = extractRpcMessage(error, "No se pudo guardar el avance.");
            this.notification.add(this.state.error, { type: "warning" });
        } finally {
            this.state.submitting = false;
        }
    }

    async onBackToSearch(skipConfirm = false) {
        if (skipConfirm !== true && !this._confirmDiscardUnsaved()) {
            return;
        }
        this._stopVoiceRecognition();
        this.clearPartida();
        this.state.error = "";
        this.state.showPartidaDropdown = false;
        this.state.inEvaluation = false;
        this._saveDraft();
    }

    async close() {
        if (!this._confirmDiscardUnsaved()) {
            return;
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
