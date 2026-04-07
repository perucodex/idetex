/** @odoo-module */

import { Component, onMounted, onWillStart, useRef, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

const SAMPLE_TYPE_OPTIONS = [
    { value: "", label: "Seleccione..." },
    { value: "acabado", label: "Acabado" },
    { value: "sanforizado_compactado", label: "Sanforizado y Compactado" },
    { value: "estampado", label: "Estampado" },
];

function normalizeText(v) {
    return (v || "").toString().toLowerCase().trim();
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

function getNowLocalInputValue() {
    const now = new Date();
    const pad = (n) => `${n}`.padStart(2, "0");
    return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}T${pad(now.getHours())}:${pad(now.getMinutes())}`;
}

function toServerDatetime(value) {
    if (!value) return false;
    const normalized = `${value}`.trim();
    if (!normalized) return false;
    return `${normalized.replace("T", " ")}:00`;
}

export class QualitySampleReceptionScreen extends Component {
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

        this.signatureCanvasRef = useRef("signatureCanvas");
        this._isDrawing = false;
        this._searchTimer = null;

        this.state = useState({
            loading: true,
            saving: false,
            searchingDni: false,
            error: "",
            partidaQuery: "",
            showPartidaDropdown: false,
            selectedPartidaId: "",
            selectedPartidaData: null,
            partidas: [],
            receptionDatetime: getNowLocalInputValue(),
            sampleType: "",
            dni: "",
            deliveryName: "",
            historyRows: [],
        });

        onWillStart(async () => {
            const initialPartidaId = Number(this.props.action?.params?.pedido_line_id || 0);
            await this._loadPartidas();
            if (initialPartidaId) {
                this.selectPartida(initialPartidaId);
            }
            this.state.loading = false;
        });

        onMounted(() => {
            this._initSignatureCanvas();
        });
    }

    get SAMPLE_TYPE_OPTIONS() {
        return SAMPLE_TYPE_OPTIONS;
    }

    get filteredPartidas() {
        const q = normalizeText(this.state.partidaQuery);
        if (!q) return (this.state.partidas || []).slice(0, 30);
        return (this.state.partidas || [])
            .filter((p) =>
                normalizeText(p.batch).includes(q)
                || normalizeText(p.customer).includes(q)
                || normalizeText(p.article).includes(q)
                || normalizeText(p.color_name).includes(q)
            )
            .slice(0, 30);
    }

    get canSave() {
        return Boolean(
            this.state.selectedPartidaId
            && this.state.receptionDatetime
            && this.state.sampleType
            && `${this.state.dni || ""}`.trim().length === 8
            && `${this.state.deliveryName || ""}`.trim()
            && !this.state.saving
        );
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

    async _loadPartidas(query = "") {
        try {
            this.state.partidas = await this.orm.call("control.sample.reception", "action_tablet_get_partidas", [query, 100]);
            this._syncSelectedPartidaData();
        } catch (error) {
            this.state.error = extractRpcMessage(error, "No se pudieron cargar las partidas.");
        }
    }

    async _loadHistory() {
        if (!this.state.selectedPartidaId) {
            this.state.historyRows = [];
            return;
        }
        try {
            const rows = await this.orm.call("control.sample.reception", "action_tablet_get_recent", [Number(this.state.selectedPartidaId), 12]);
            this.state.historyRows = rows || [];
        } catch {
            this.state.historyRows = [];
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
                this.state.sampleType = "";
                this.state.historyRows = [];
            }
        }
        this.state.showPartidaDropdown = Boolean(value) && !this.state.selectedPartidaId;
        if (this._searchTimer) clearTimeout(this._searchTimer);
        this._searchTimer = setTimeout(() => this.searchPartidas(value), 250);
    }

    onPartidaInputFocus() {
        if (!this.state.selectedPartidaId && this.state.partidaQuery) {
            this.state.showPartidaDropdown = true;
        }
    }

    async searchPartidas(query) {
        try {
            await this._loadPartidas((query || "").trim());
        } finally {
            // no-op
        }
    }

    clearPartida() {
        this.state.selectedPartidaId = "";
        this.state.selectedPartidaData = null;
        this.state.partidaQuery = "";
        this.state.sampleType = "";
        this.state.historyRows = [];
    }

    selectPartida(partidaId) {
        const id = Number(partidaId || 0);
        const previousId = this.state.selectedPartidaId;
        this.state.selectedPartidaId = `${id}`;
        this._syncSelectedPartidaData();
        if (String(previousId || "") !== String(partidaId || "")) {
            this.state.sampleType = "";
        }
        this.state.showPartidaDropdown = false;
        this._loadHistory();
    }

    onDniInput(ev) {
        this.state.dni = `${ev.target.value || ""}`.replace(/\D+/g, "").slice(0, 8);
    }

    onSampleTypeChange(ev) {
        this.state.sampleType = (ev.target.value || "").trim();
    }

    async onLookupDni() {
        if (`${this.state.dni || ""}`.trim().length !== 8) {
            this.notification.add("Ingrese un DNI valido de 8 digitos.", { type: "warning" });
            return;
        }
        this.state.searchingDni = true;
        try {
            const payload = await this.orm.call("control.sample.reception", "action_tablet_lookup_dni", [this.state.dni]);
            this.state.dni = payload?.dni || this.state.dni;
            this.state.deliveryName = payload?.name || this.state.deliveryName;
            this.notification.add("DNI validado correctamente.", { type: "success" });
        } catch (error) {
            this.notification.add(extractRpcMessage(error, "No se pudo consultar el DNI."), { type: "danger" });
        } finally {
            this.state.searchingDni = false;
        }
    }

    _initSignatureCanvas() {
        const canvas = this.signatureCanvasRef.el;
        if (!canvas) return;

        const ratio = Math.max(window.devicePixelRatio || 1, 1);
        const rect = canvas.getBoundingClientRect();
        canvas.width = Math.floor(rect.width * ratio);
        canvas.height = Math.floor(rect.height * ratio);

        const ctx = canvas.getContext("2d");
        if (!ctx) return;
        ctx.scale(ratio, ratio);
        ctx.lineCap = "round";
        ctx.lineJoin = "round";
        ctx.lineWidth = 2;
        ctx.strokeStyle = "#111827";

        const start = (x, y) => {
            this._isDrawing = true;
            ctx.beginPath();
            ctx.moveTo(x, y);
        };

        const move = (x, y) => {
            if (!this._isDrawing) return;
            ctx.lineTo(x, y);
            ctx.stroke();
        };

        const stop = () => {
            this._isDrawing = false;
            ctx.closePath();
        };

        const getPos = (event) => {
            const bounds = canvas.getBoundingClientRect();
            return {
                x: event.clientX - bounds.left,
                y: event.clientY - bounds.top,
            };
        };

        canvas.addEventListener("pointerdown", (event) => {
            const p = getPos(event);
            start(p.x, p.y);
        });
        canvas.addEventListener("pointermove", (event) => {
            const p = getPos(event);
            move(p.x, p.y);
        });
        canvas.addEventListener("pointerup", stop);
        canvas.addEventListener("pointerleave", stop);
    }

    clearSignature() {
        const canvas = this.signatureCanvasRef.el;
        if (!canvas) return;
        const ctx = canvas.getContext("2d");
        if (!ctx) return;
        ctx.clearRect(0, 0, canvas.width, canvas.height);
    }

    _getSignatureBase64() {
        const canvas = this.signatureCanvasRef.el;
        if (!canvas) return "";

        // Validate whether there is any stroke drawn by checking alpha channel.
        const ctx = canvas.getContext("2d");
        const pixels = ctx.getImageData(0, 0, canvas.width, canvas.height).data;
        let hasInk = false;
        for (let idx = 3; idx < pixels.length; idx += 4) {
            if (pixels[idx] > 0) {
                hasInk = true;
                break;
            }
        }
        if (!hasInk) return "";

        const dataUrl = canvas.toDataURL("image/png");
        return dataUrl.split(",")[1] || "";
    }

    async saveReception() {
        if (!this.canSave) return;

        const signature = this._getSignatureBase64();
        if (!signature) {
            this.notification.add("Debe registrar la firma antes de guardar.", { type: "warning" });
            return;
        }

        this.state.saving = true;
        this.state.error = "";
        try {
            await this.orm.call("control.sample.reception", "action_tablet_register", [
                Number(this.state.selectedPartidaId),
                this.state.dni,
                this.state.deliveryName,
                signature,
                toServerDatetime(this.state.receptionDatetime),
                this.state.sampleType,
            ]);

            this.notification.add("Recepcion registrada correctamente.", { type: "success" });
            this.state.dni = "";
            this.state.deliveryName = "";
            this.state.receptionDatetime = getNowLocalInputValue();
            this.clearSignature();
            await this._loadHistory();
        } catch (error) {
            this.state.error = extractRpcMessage(error, "No se pudo registrar la recepcion.");
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

QualitySampleReceptionScreen.template = "idtx_batch_quality.QualitySampleReceptionScreen";

registry.category("actions").add("idtx_quality.sample_reception_screen", QualitySampleReceptionScreen);
