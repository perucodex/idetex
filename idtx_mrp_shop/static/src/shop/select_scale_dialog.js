/** @odoo-module */

import { _t } from "@web/core/l10n/translation";
import { isDisplayStandalone } from "@web/core/browser/feature_detection";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { useService } from "@web/core/utils/hooks";
import { onWillStart, useState, onMounted, useRef, onWillUnmount } from "@odoo/owl";

export class SelectScaleDialog extends ConfirmationDialog {
    static template = "idtx_mrp_shop.SelectScaleDialog";

    static props = {
        ...ConfirmationDialog.props,
        body: { type: String, optional: true },
        scales: { type: Array, optional: true },
        employees: { type: Array, optional: true },
        equipments: { type: Array, optional: true },
        employee_ids: { type: Array, optional: true },
        equipment_ids: { type: Array, optional: true },
        disabled: { type: Array, optional: true },
        active: { type: Array, optional: true },
        radioMode: { type: Boolean, default: false, optional: true },
        showWarning: { type: Boolean, default: false, optional: true },
        selectedEmployee: { type: [Number, String], optional: true },
        selectedEquipment: { type: [Number, String], optional: true },
        selectedOption: { type: [Number, String], optional: true },
        options: { type: Array, optional: true },
    };

    setup() {
        super.setup();

        this.ormService = useService("orm");
        this.menu = useService("menu");
        this.notification = useService("notification");

        this.scales = this.props.scales || [];
        this.options = this.props.options || [];

        const initialOption = this.props.selectedOption ? String(this.props.selectedOption) : "";

        this.state = useState({
            selectedEmployee: this.props.selectedEmployee ? String(this.props.selectedEmployee) : "",
            selectedEquipment: this.props.selectedEquipment ? String(this.props.selectedEquipment) : "",
            selectedOption: initialOption,
            optionTouched: !!initialOption,
            // Al intentar confirmar con campos faltantes, se marcan en rojo
            // (is-invalid) y el diálogo NO se cierra.
            triedConfirm: false,
            employees: this.props.employees || [],

            // Plan de rollos de la OT (para el mensaje de rollos pendientes).
            woPlan: null,

            selectedMode: "manual",
            selectedScaleId: null,

            // En scale = readonly (peso en vivo), en manual = editable
            manualWeight: "",

            // auth manual
            isManualAuthorized: false,
            authLogin: "",
            authPassword: "",
            authError: "",
            isAuthChecking: false,

            // equipos reactivos
            equipments: this.props.equipments || [],

            // lectura en vivo
            scaleReadError: "",
            scaleUnit: "kg",
            isScaleReading: false,
            scaleStable: null,
            scaleAgeS: null,

            // lectura por puerto COM del navegador (Web Serial)
            serialConnected: false,
        });

        this.isDisplayStandalone = isDisplayStandalone();

        this.manualInputRef = useRef("manualInput");
        this.authLoginRef = useRef("authLogin");
        this.authPasswordRef = useRef("authPassword");

        this._scalePollTimer = null;
        this._scalePollInProgress = false;
        this._autoCloseTimer = null;
        this._isConfirmed = false;
        // true si la balanza se restauró desde localStorage (evita que el
        // default "primera balanza" pise una restauración a Manual).
        this._scaleRestored = false;

        // Web Serial (puerto COM leído por el navegador)
        this._serialPort = null;
        this._serialReader = null;
        this._serialStop = false;
        this._serialBaudrate = 9600;

        onMounted(() => {
            this._startAutoCloseTimer();
            if (this.manualInputRef.el) {
                this.manualInputRef.el.focus();
                this.manualInputRef.el.select();
            }
        });

        onWillUnmount(() => {
            this._clearAutoCloseTimer();
            this._stopScalePolling();
            this._stopSerial();
        });

        onWillStart(async () => {
            if (!this.scales.length) {
                await this._loadScales();
            }
            if (!this.options.length) {
                await this._loadOptions();
            } else {
                await this._hydrateOptions();
            }

            // ✅ Restaurar selección persistida por workorder
            this._restoreSelectionFromLocalStorage();

            await this._syncResourcesFromOption(this.state.selectedOption, { preserveSelection: true });

            // Si hay opción seleccionada, sincroniza equipment SOLO si no hay equipment ya seleccionado
            // Primera balanza por defecto (respeta su modo de lectura)
            if (this.scales.length && !this.state.selectedScaleId && !this._scaleRestored) {
                const first = this.scales[0];
                this.state.selectedScaleId = first.id;
                if (first.read_mode === "serial") {
                    this.state.selectedMode = "serial";
                    this._serialBaudrate = first.serial_baudrate || 9600;
                } else {
                    this.state.selectedMode = "scale";
                }
            }

            // auth manual persistida en sesión
            try {
                const ok = await this.ormService.call("res.users", "is_manual_access_enabled", []);
                this.state.isManualAuthorized = !!ok;
            } catch (e) {
                this.state.isManualAuthorized = false;
            }

            if (this.state.selectedMode === "scale" && this.state.selectedScaleId) {
                await this._startScalePolling();
            } else if (this.state.selectedMode === "serial" && this.state.selectedScaleId) {
                await this._autoConnectSerial();
            }
        });

        // Plan de rollos de la OT: se lee para calcular en vivo cuántos rollos
        // faltan por tejer (sumando los PESOS REALES ya tejidos, no un conteo).
        onWillStart(async () => {
            const woId = this._getWorkorderId();
            if (!woId) return;
            try {
                const [wo] = await this.ormService.read(
                    "mrp.workorder", [woId],
                    ["operation_type", "weave_type", "qty_production",
                     "estimated_weight_per_roll", "qty_produced"]
                );
                this.state.woPlan = wo || null;
            } catch (e) {
                this.state.woPlan = null;
            }
        });
    }

    // Mensaje de rollos pendientes: descuenta la SUMA de pesos reales ya
    // tejidos (qty_produced) del total a producir, y parte el resto en rollos
    // completos del peso estimado + un rollo final con el sobrante (cuyo valor
    // va cambiando según los pesos reales acumulados).
    get pendingRollsMessage() {
        const wo = this.state.woPlan;
        if (!wo || wo.operation_type !== "weaving" || wo.weave_type === "rect") {
            return "";
        }
        const peso = wo.estimated_weight_per_roll || 0;
        const qty = wo.qty_production || 0;
        if (peso <= 0 || qty <= 0) return "";
        const sumWoven = wo.qty_produced || 0;
        const remaining = qty - sumWoven;
        if (remaining <= 0.001) {
            return "Producción de rollos completa.";
        }
        const full = Math.floor(remaining / peso);
        const leftover = remaining - full * peso;
        const parts = [];
        if (full > 0) {
            parts.push(`${full} ${full === 1 ? "rollo" : "rollos"} de ${peso.toFixed(2)} kg`);
        }
        if (leftover > 0.001) {
            parts.push(`1 rollo de ${leftover.toFixed(2)} kg`);
        }
        return `Faltan por tejer ${parts.join(" + ")} (faltan ${remaining.toFixed(2)} kg).`;
    }

    // =========================
    // Persistencia (FIX)
    // =========================
    _getWorkorderId() {
        return this.props.active && this.props.active.length ? this.props.active[0] : null;
    }

    _getLSKey() {
        const wo = this._getWorkorderId();
        return wo ? `idtx_mrp.last_selection.${wo}` : "idtx_mrp.last_selection";
    }

    _restoreSelectionFromLocalStorage() {
        try {
            const LS_KEY = this._getLSKey();
            const raw = window.localStorage.getItem(LS_KEY);
            // Sin registro de esta OT igual se sigue: la balanza tiene
            // fallback global (última usada en la estación).
            const parsed = raw ? JSON.parse(raw) : {};

            // Employee
            if (!this.state.selectedEmployee && parsed.employee_id) {
                const existsEmp = (this.state.employees || []).some(e => String(e.id) === String(parsed.employee_id));
                if (existsEmp) this.state.selectedEmployee = String(parsed.employee_id);
            }

            // Equipment
            if (!this.state.selectedEquipment && parsed.equipment_id) {
                const existsEq = (this.state.equipments || []).some(e => String(e.id) === String(parsed.equipment_id));
                if (existsEq) this.state.selectedEquipment = String(parsed.equipment_id);
            }

            // Option
            if (parsed.option_id) {
                const foundOpt = (this.options || []).some(o => String(o.id) === String(parsed.option_id));
                if (foundOpt) {
                    this.state.selectedOption = String(parsed.option_id);
                    this.state.optionTouched = true;
                }
            }

            // Balanza: la del workorder; si esta OT aún no tiene, la última
            // usada en esta estación (clave global).
            this._restoreScaleSelection(parsed);
        } catch (e) {
            // ignore
        }
    }

    _restoreScaleSelection(parsed) {
        let scaleVal = parsed.scale_id || "";
        if (!scaleVal) {
            scaleVal = window.localStorage.getItem("idtx_mrp.last_scale") || "";
        }
        if (scaleVal === "manual") {
            this.state.selectedMode = "manual";
            this.state.selectedScaleId = null;
            this._scaleRestored = true;
        } else if (scaleVal) {
            const scale = (this.scales || []).find(s => String(s.id) === String(scaleVal));
            if (scale) {
                this.state.selectedScaleId = scale.id;
                if (scale.read_mode === "serial") {
                    this.state.selectedMode = "serial";
                    this._serialBaudrate = scale.serial_baudrate || 9600;
                } else {
                    this.state.selectedMode = "scale";
                }
                this._scaleRestored = true;
            }
        }
    }

    _persistScaleSelection() {
        // La balanza es de la estación física: se guarda por workorder (como
        // empleado/equipo) y además en una clave global como default para
        // workorders nuevos.
        try {
            const scaleVal = this.state.selectedMode === "manual"
                ? "manual"
                : (this.state.selectedScaleId ? String(this.state.selectedScaleId) : "");
            if (!scaleVal) return;
            const key = this._getLSKey();
            const raw = window.localStorage.getItem(key);
            const parsed = raw ? JSON.parse(raw) : {};
            parsed.scale_id = scaleVal;
            window.localStorage.setItem(key, JSON.stringify(parsed));
            window.localStorage.setItem("idtx_mrp.last_scale", scaleVal);
        } catch (e) {
            // ignore
        }
    }

    _persistSelectionPartial({ includeEmpty = false } = {}) {
        // includeEmpty=false => NO pisa con vacío/false (este es el fix clave)
        try {
            const LS_KEY = this._getLSKey();
            const raw = window.localStorage.getItem(LS_KEY);
            const parsed = raw ? JSON.parse(raw) : {};

            if (includeEmpty) {
                parsed.employee_id = this.state.selectedEmployee ? String(this.state.selectedEmployee) : false;
                parsed.equipment_id = this.state.selectedEquipment ? String(this.state.selectedEquipment) : false;
                parsed.option_id = this.state.selectedOption ? String(this.state.selectedOption) : false;
            } else {
                if (this.state.selectedEmployee) parsed.employee_id = String(this.state.selectedEmployee);
                if (this.state.selectedEquipment) parsed.equipment_id = String(this.state.selectedEquipment);
                if (this.state.selectedOption) parsed.option_id = String(this.state.selectedOption);
            }

            window.localStorage.setItem(LS_KEY, JSON.stringify(parsed));
        } catch (e) {
            // ignore
        }
    }

    // =========================
    // UI / Confirm enabled
    // =========================
    get appName() {
        return encodeURIComponent(this.menu.getCurrentApp().name);
    }

    get isConfirmEnabled() {
        if (!this.state.selectedEmployee || !this.state.selectedEquipment) return false;

        const w = parseFloat(this.state.manualWeight || "");

        if (this.state.selectedMode === "scale" || this.state.selectedMode === "serial") {
            if (this.state.selectedMode === "scale" && !this.state.selectedScaleId) return false;
            if (this.state.selectedMode === "serial" && !this.state.serialConnected) return false;
            if (this.state.scaleReadError) return false;
            if (isNaN(w) || w <= 0) return false;
            if (this.state.scaleStable === false) return false;
            return true;
        }

        if (!this.state.isManualAuthorized) return false;
        return !isNaN(w) && w > 0;
    }

    // =========================
    // Campos requeridos en rojo (estilo backend). Solo tras intentar confirmar;
    // se limpian solos al corregir el valor.
    // =========================
    get isOptionInvalid() {
        return this.state.triedConfirm && (this.options || []).length > 0 && !this.state.selectedOption;
    }

    get isEmployeeInvalid() {
        return this.state.triedConfirm && !this.state.selectedEmployee;
    }

    get isEquipmentInvalid() {
        return this.state.triedConfirm && !this.state.selectedEquipment;
    }

    get isWeightInvalid() {
        if (!this.state.triedConfirm) return false;
        const w = parseFloat(this.state.manualWeight || "");
        if (isNaN(w) || w <= 0) return true;
        if (this.state.selectedMode === "scale" || this.state.selectedMode === "serial") {
            return !!this.state.scaleReadError || this.state.scaleStable === false;
        }
        return !this.state.isManualAuthorized;
    }

    // =========================
    // Handlers de Employee/Equipment (persistencia inmediata)
    // =========================
    onEmployeeChange(ev) {
        this.state.selectedEmployee = ev?.target?.value || "";
        this._persistSelectionPartial(); // NO borra si está vacío
    }

    onEquipmentChange(ev) {
        this.state.selectedEquipment = ev?.target?.value || "";
        this._persistSelectionPartial(); // NO borra si está vacío
    }

    async onScaleSelectChange(ev) {
        const val = ev?.target?.value || "";
        if (val === "manual") {
            await this.selectManual();
        } else {
            const scale = (this.scales || []).find(s => String(s.id) === val);
            if (scale) {
                await this.selectScale(scale);
            }
        }
        this._persistScaleSelection();
    }

    // =========================
    // Polling scale
    // =========================
    async _startScalePolling() {
        this._stopScalePolling();
        await this._pollScaleWeight();
        this._scalePollTimer = setInterval(() => this._pollScaleWeight(), 700);
    }

    _stopScalePolling() {
        if (this._scalePollTimer) {
            clearInterval(this._scalePollTimer);
            this._scalePollTimer = null;
        }
        this._scalePollInProgress = false;
    }

    // Cierra la ventana automáticamente tras 1min de inactividad (FIX)
    _startAutoCloseTimer() {
        this._clearAutoCloseTimer();
        this._autoCloseTimer = setTimeout(() => {
            if (!this._isConfirmed) {
                this.props.close();
            }
        }, 60000);
    }

    _clearAutoCloseTimer() {
        if (this._autoCloseTimer) {
            clearTimeout(this._autoCloseTimer);
            this._autoCloseTimer = null;
        }
    }

    async _pollScaleWeight() {
        if (this._scalePollInProgress) return;
        if (this.state.selectedMode !== "scale" || !this.state.selectedScaleId) return;

        this._scalePollInProgress = true;
        this.state.isScaleReading = true;

        let timeoutId = null;
        try {
            const controller = new AbortController();
            timeoutId = setTimeout(() => controller.abort(), 1800);

            const url = `/idtx_scale/peso?scale_id=${encodeURIComponent(this.state.selectedScaleId)}&max_age=1.5&_=${Date.now()}`;
            const resp = await fetch(url, { method: "GET", cache: "no-store", signal: controller.signal });

            if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
            const data = await resp.json();

            if (data?.ok && data?.peso !== null && data?.peso !== undefined && !isNaN(Number(data.peso))) {
                this.state.manualWeight = String(Number(data.peso).toFixed(2));
                this.state.scaleUnit = data.unidad || "kg";
                this.state.scaleStable = (typeof data.stable === "boolean") ? data.stable : null;
                this.state.scaleAgeS = (typeof data.age_s === "number") ? data.age_s : null;
                this.state.scaleReadError = "";
            } else {
                this.state.scaleStable = (typeof data?.stable === "boolean") ? data.stable : null;
                this.state.scaleAgeS = (typeof data?.age_s === "number") ? data.age_s : null;
                this.state.scaleReadError = data?.error || _t("No communication with the scale");
            }
        } catch (e) {
            this.state.scaleReadError = _t("Error reading scale");
            this.state.scaleStable = null;
            this.state.scaleAgeS = null;
        } finally {
            if (timeoutId) clearTimeout(timeoutId);
            this.state.isScaleReading = false;
            this._scalePollInProgress = false;
        }
    }

    // =========================
    // Option change (FIX: no borrar employee/equipment)
    // =========================
    async onOptionChange(ev) {
        this.state.selectedOption = ev?.target?.value || "";
        this.state.optionTouched = true;

        await this._syncResourcesFromOption(this.state.selectedOption);

        // ✅ Persistir la opción SIN pisar employee/equipment si están vacíos
        this._persistSelectionPartial();
    }

    // =========================
    // Manual / Scale switch
    // =========================
    async selectManual() {
        this._stopScalePolling();
        await this._stopSerial();

        this.state.selectedMode = "manual";
        this.state.selectedScaleId = null;
        this.state.manualWeight = "";
        this.state.authError = "";
        this.state.isAuthChecking = false;
        this.state.scaleReadError = "";
        this.state.scaleStable = null;
        this.state.scaleAgeS = null;

        setTimeout(() => {
            try {
                if (this.state.isManualAuthorized) {
                    if (this.manualInputRef?.el) {
                        this.manualInputRef.el.focus();
                        this.manualInputRef.el.select();
                    }
                } else if (this.authLoginRef?.el) {
                    this.authLoginRef.el.focus();
                    this.authLoginRef.el.select();
                }
            } catch (e) {}
        }, 0);
    }

    async selectScale(scale) {
        // Al cambiar de balanza, cortar cualquier lectura previa (IP o COM).
        this._stopScalePolling();
        await this._stopSerial();

        this.state.selectedScaleId = scale.id;

        this.state.authError = "";
        this.state.isAuthChecking = false;
        this.state.authPassword = "";

        this.state.scaleReadError = "";
        this.state.scaleStable = null;
        this.state.scaleAgeS = null;
        this.state.manualWeight = "";

        if (scale.read_mode === "serial") {
            this.state.selectedMode = "serial";
            this._serialBaudrate = scale.serial_baudrate || 9600;
            this._autoConnectSerial();
        } else {
            this.state.selectedMode = "scale";
            this._startScalePolling();
        }
    }

    // =========================
    // Web Serial (puerto COM leído por el navegador)
    // =========================
    // Reconecta sin diálogo si ya se autorizó el puerto en este origen.
    async _autoConnectSerial() {
        if (!navigator.serial) {
            this.state.scaleReadError = _t(
                "Este navegador no soporta lectura de puerto COM. Usa Chrome o Edge de escritorio.");
            return;
        }
        try {
            const ports = await navigator.serial.getPorts();
            if (ports && ports.length) {
                await this._openSerialPort(ports[0]);
            }
        } catch (e) {
            // Sin puerto autorizado aún: el usuario debe pulsar "Conectar".
        }
    }

    // Requiere gesto del usuario (click): muestra el selector de puertos.
    async connectSerial() {
        if (!navigator.serial) {
            this.state.scaleReadError = _t(
                "Este navegador no soporta lectura de puerto COM. Usa Chrome o Edge de escritorio.");
            return;
        }
        try {
            const port = await navigator.serial.requestPort();
            await this._openSerialPort(port);
        } catch (e) {
            // El usuario canceló el selector o el puerto no se pudo abrir.
            this.state.scaleReadError = _t("No se pudo abrir el puerto COM.");
        }
    }

    async _openSerialPort(port) {
        try {
            await port.open({
                baudRate: this._serialBaudrate || 9600,
                dataBits: 8,
                parity: "none",
                stopBits: 1,
            });
        } catch (e) {
            this.state.scaleReadError = _t("No se pudo abrir el puerto COM.");
            return;
        }
        this._serialPort = port;
        this._serialStop = false;
        this.state.serialConnected = true;
        this.state.scaleReadError = "";
        this.state.scaleUnit = "kg";
        this._serialReadLoop();
    }

    async _serialReadLoop() {
        const decoder = new TextDecoder();
        let reader;
        try {
            reader = this._serialPort.readable.getReader();
        } catch (e) {
            this.state.scaleReadError = _t("Error leyendo el puerto COM.");
            return;
        }
        this._serialReader = reader;
        let buffer = "";
        try {
            while (!this._serialStop) {
                const { value, done } = await reader.read();
                if (done) break;
                if (value) {
                    buffer += decoder.decode(value, { stream: true });
                    const lines = buffer.split(/\r\n|\r|\n/);
                    buffer = lines.pop(); // la última puede estar incompleta
                    for (const line of lines) {
                        this._handleSerialLine(line);
                    }
                }
            }
        } catch (e) {
            if (!this._serialStop) {
                this.state.scaleReadError = _t("Error leyendo el puerto COM.");
            }
        } finally {
            try { reader.releaseLock(); } catch (e) {}
        }
    }

    _handleSerialLine(line) {
        const weight = this._parseSerialWeight(line);
        const stable = this._parseSerialStability(line);
        if (stable !== null) {
            this.state.scaleStable = stable;
        }
        if (weight !== null) {
            this.state.manualWeight = weight.toFixed(2);
            this.state.scaleUnit = "kg";
            this.state.scaleReadError = "";
        }
    }

    // Mismo parseo que script_balanza/balanza.py (varios formatos con KG).
    _parseSerialWeight(line) {
        if (!line) return null;
        const clean = line.replace(/\x00/g, "").replace(/,/g, ".").trim();
        const m = clean.match(/(-?\d+(?:\.\d+)?)\s*KG/i);
        if (!m) return null;
        const v = parseFloat(m[1]);
        return isNaN(v) ? null : v;
    }

    _parseSerialStability(line) {
        if (!line) return null;
        const up = line.trim().toUpperCase();
        if (up.startsWith("ST")) return true;   // estable
        if (up.startsWith("US")) return false;  // inestable
        return null;
    }

    async _stopSerial() {
        this._serialStop = true;
        this.state.serialConnected = false;
        try {
            if (this._serialReader) {
                await this._serialReader.cancel();
                try { this._serialReader.releaseLock(); } catch (e) {}
            }
        } catch (e) {}
        this._serialReader = null;
        try {
            if (this._serialPort) {
                await this._serialPort.close();
            }
        } catch (e) {}
        this._serialPort = null;
    }

    // =========================
    // Manual auth
    // =========================
    async confirmManualAuth() {
        if (!this.state.authLogin || !this.state.authPassword) return;

        this.state.isAuthChecking = true;
        this.state.authError = "";

        try {
            await this.ormService.call("res.users", "validate_manual_access", [this.state.authLogin, this.state.authPassword]);
            this.state.isManualAuthorized = true;
            this.state.authPassword = "";

            setTimeout(() => {
                try {
                    if (this.manualInputRef?.el) {
                        this.manualInputRef.el.focus();
                        this.manualInputRef.el.select();
                    }
                } catch (e) {}
            }, 0);
        } catch (e) {
            this.state.isManualAuthorized = false;
            this.state.authError = _t("Acceso denegado: se requiere MRP Manager.");
        } finally {
            this.state.isAuthChecking = false;
        }
    }

    onAuthKeyDown(ev) {
        if (ev.key === "Enter") this.confirmManualAuth();
    }

    async deactivateManual() {
        try {
            await this.ormService.call("res.users", "disable_manual_access", []);
        } catch (e) {}

        this.state.isManualAuthorized = false;
        this.state.manualWeight = "";
        this.state.authLogin = "";
        this.state.authPassword = "";
        this.state.authError = "";
        this.state.isAuthChecking = false;

        this.state.selectedMode = "manual";

        setTimeout(() => {
            try {
                if (this.authLoginRef?.el) {
                    this.authLoginRef.el.focus();
                    this.authLoginRef.el.select();
                }
            } catch (e) {}
        }, 0);
    }

    onManualInput(ev) {
        let v = ev.target.value;
        v = v.replace(/,/g, ".");
        v = v.replace(/[^0-9.]/g, "");
        const parts = v.split(".");
        if (parts.length > 2) v = parts[0] + "." + parts.slice(1).join("");
        this.state.manualWeight = v;
    }

    onInputKeyDown(ev) {
        if (ev.key === "Enter" && this.isConfirmEnabled) this.confirm();
    }

    // Payload que se envía al confirmar (las subclases pueden extenderlo,
    // p.ej. SelectSizeDialog agrega talla y cantidad).
    _getConfirmPayload(w) {
        return {
            // En serial también se envía la balanza: el peso viaja como
            // manual_weight y el backend usa scale.printer_ip para imprimir.
            scale_id: (this.state.selectedMode === "scale" || this.state.selectedMode === "serial")
                ? this.state.selectedScaleId : false,
            employee_id: this.state.selectedEmployee || false,
            equipment_id: this.state.selectedEquipment || false,
            option_id: this.state.selectedOption || false,
            manual_weight: !isNaN(w) ? w : false,
        };
    }

    // =========================
    // Confirm
    // =========================
    confirm() {
        this.state.triedConfirm = true;
        // La opción es requerida cuando la OT tiene opciones (el roll de tejido
        // la exige en el backend; validarla aquí evita que el diálogo se cierre
        // y el error llegue después).
        if ((this.options || []).length > 0 && !this.state.selectedOption) {
            this.notification.add(_t("You must select an option."), { type: "danger" });
            return;
        }
        if (!this.state.selectedEmployee) {
            this.notification.add(_t("You must select an employee."), { type: "danger" });
            return;
        }
        if (!this.state.selectedEquipment) {
            this.notification.add(_t("You must select an equipment."), { type: "danger" });
            return;
        }

        const w = parseFloat(this.state.manualWeight || "");

        if (this.state.selectedMode === "serial" && !this.state.serialConnected) {
            this.notification.add(_t("Conecta el puerto COM primero."), { type: "danger" });
            return;
        }

        if (this.state.selectedMode === "scale" || this.state.selectedMode === "serial") {
            if (this.state.scaleReadError) {
                this.notification.add(_t("Scale is not available."), { type: "danger" });
                return;
            }
            if (isNaN(w) || w <= 0) {
                this.notification.add(_t("No valid live weight from scale."), { type: "danger" });
                return;
            }
            if (this.state.scaleStable === false) {
                this.notification.add(_t("Weight is unstable. Please wait until it stabilizes."), { type: "warning" });
                return;
            }
        }

        if (this.state.selectedMode === "manual") {
            if (!this.state.isManualAuthorized) {
                this.notification.add(_t("Manual mode requires authorization."), { type: "danger" });
                return;
            }
            if (isNaN(w) || w <= 0) {
                this.notification.add(_t("You must enter a valid manual weight."), { type: "danger" });
                return;
            }
        }

        const payload = this._getConfirmPayload(w);

        // ✅ Persistir full (aquí sí permitimos vacíos si quieres, pero normalmente ya no estarán vacíos)
        this._persistSelectionPartial({ includeEmpty: true });
        this._persistScaleSelection();

        this._isConfirmed = true;
        this._clearAutoCloseTimer();
        this._stopScalePolling();
        this.props.confirm(payload);
        this.props.close();
    }

    // =========================
    // Loaders
    // =========================
    async _loadScales() {
        const scales = await this.ormService.searchRead(
            "scale.registry", [], ["equipment_id", "read_mode", "serial_baudrate"]);
        const equipmentIds = scales.map(s => s.equipment_id?.[0]).filter(Boolean);

        const equipments = equipmentIds.length
            ? await this.ormService.read("maintenance.equipment", equipmentIds, ["name"])
            : [];
        const equipmentMap = Object.fromEntries(equipments.map(e => [e.id, e.name]));

        this.scales = scales.map(s => ({
            ...s,
            read_mode: s.read_mode || "ip",
            serial_baudrate: s.serial_baudrate || 9600,
            equipment_name: equipmentMap[s.equipment_id?.[0]] || "",
        }));

        if (!this.scales.length) {
            this.notification.add(
                _t("No scales are available, please create one first to add it to the shop floor view"),
                { type: "danger" }
            );
        }
    }

    async _loadEmployees(employeeIds = []) {
        const ids = (employeeIds || []).filter(Boolean);
        this.state.employees = ids.length
            ? await this.ormService.searchRead("hr.employee", [["id", "in", ids]], ["name"])
            : [];
        if (!this.state.employees.length) {
            this.notification.add(
                _t("No employees are available, please assign one first to add it to the shop floor view"),
                { type: "danger" }
            );
        }
    }

    async _loadEquipments(equipmentIds = []) {
        const ids = (equipmentIds || []).filter(Boolean);
        this.state.equipments = ids.length
            ? await this.ormService.searchRead("maintenance.equipment", [["id", "in", ids]], ["name"])
            : [];
        if (!this.state.equipments.length) {
            this.notification.add(
                _t("No equipments are available, please assign one first to add it to the shop floor view"),
                { type: "danger" }
            );
        }
    }

    async _loadOptions() {
        try {
            const workorderId = this._getWorkorderId();
            if (workorderId) {
                const raw = await this.ormService.searchRead(
                    "mrp.workorder.option",
                    [["workorder_id", "=", workorderId]],
                    ["name", "id", "employee_ids", "equipment_ids"]
                );
                this.options = (raw || []).filter(opt => opt && opt.id);
            } else {
                this.options = [];
            }
        } catch (e) {
            this.options = [];
        }

        if (!this.options.length) {
            this.notification.add(
                _t("No options are available for this work order."),
                { type: "warning" }
            );
        }
    }

    async _syncResourcesFromOption(optionId = null, { preserveSelection = false } = {}) {
        const selectedOptionId = optionId ?? this.state.selectedOption;
        const selected = selectedOptionId
            ? this.options.find(o => String(o.id) === String(selectedOptionId))
            : null;

        const employeeIds = selected
            ? (selected.employee_ids || [])
            : this._getAllOptionEmployeeIds();
        const equipmentIds = selected
            ? (selected.equipment_ids || [])
            : this._getAllOptionEquipmentIds();

        await this._loadEmployees(employeeIds);
        await this._loadEquipments(equipmentIds);

        const validEmployeeIds = new Set((this.state.employees || []).map(e => String(e.id)));
        const validEquipmentIds = new Set((this.state.equipments || []).map(e => String(e.id)));

        if (!preserveSelection || !validEmployeeIds.has(String(this.state.selectedEmployee || ""))) {
            this.state.selectedEmployee = "";
        }
        if (!preserveSelection || !validEquipmentIds.has(String(this.state.selectedEquipment || ""))) {
            this.state.selectedEquipment = "";
        }

        this._persistSelectionPartial();
    }

    async _hydrateOptions() {
        const optionIds = (this.options || []).map(o => o.id).filter(Boolean);
        if (!optionIds.length) return;

        try {
            const raw = await this.ormService.read("mrp.workorder.option", optionIds, ["name", "id", "employee_ids", "equipment_ids"]);
            this.options = (raw || []).filter(opt => opt && opt.id);
        } catch (e) {
            // ignore
        }
    }

    _getAllOptionEmployeeIds() {
        const ids = new Set();
        for (const option of this.options || []) {
            for (const employeeId of option.employee_ids || []) {
                ids.add(employeeId);
            }
        }
        return [...ids];
    }

    _getAllOptionEquipmentIds() {
        const ids = new Set();
        for (const option of this.options || []) {
            for (const equipmentId of option.equipment_ids || []) {
                ids.add(equipmentId);
            }
        }
        return [...ids];
    }
}
