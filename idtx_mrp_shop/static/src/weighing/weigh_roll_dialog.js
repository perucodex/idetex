/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { onWillStart, useRef } from "@odoo/owl";
import { SelectScaleDialog } from "../shop/select_scale_dialog";

/**
 * Diálogo de PESADO DE ROLLOS TERMINADOS: hereda del diálogo de balanza del
 * Taller toda la lectura de peso (balanza por IP con polling, puerto COM por
 * Web Serial, manual con autorización, persistencia de balanza por estación)
 * y reemplaza Opción/Empleado/Equipo por Partida + Producto.
 */
export class WeighRollDialog extends SelectScaleDialog {
    static template = "idtx_mrp_shop.WeighRollDialog";
    // mode: "weigh" (pesar rollo nuevo) | "resolve" (repesar un observado y darle grado)
    static props = { ...SelectScaleDialog.props, mode: { type: String, optional: true } };

    // El botón Pesar se rearma cuando la balanza baja de este peso (kg):
    // evita registrar dos veces el mismo rollo sin haberlo retirado.
    static ZERO_THRESHOLD = 0.2;

    setup() {
        super.setup();
        // Partida: buscador con autocompletado (no un desplegable con todas
        // las partidas abiertas — en planta son cientos). Mismo patrón que la
        // pantalla de Estabilidad/Revirado de Calidad.
        this.state.batches = [];
        this.state.selectedBatch = "";
        this.state.batchQuery = "";
        this.state.selectedBatchData = null;
        this.state.showBatchDropdown = false;
        this.state.isSearchingBatch = false;
        this._batchSearchTimer = null;
        this.state.products = [];
        this.state.selectedProduct = "";
        // Rollo CRUDO que se está pesando (opcional): trazabilidad y talla.
        this.state.rolls = [];
        this.state.selectedRoll = "";
        // true tras un pesado exitoso: bloquea Pesar hasta que la balanza
        // vuelva a 0 (retirar el rollo).
        this.state.waitingZero = false;
        // true mientras el pesado está EN CURSO (RPC): bloquea Pesar desde
        // el clic mismo — sin esto, un doble clic durante la llamada creaba
        // un segundo rollo con el mismo peso.
        this.state.weighing = false;
        // Modo desarrollador: permite pesar SIN imprimir el sticker
        // (pruebas sin gastar etiquetas).
        this.state.printSticker = true;
        // N° de rollo de Acabado (correlativo del lote) y su info del servidor
        // (¿ya pesado? ¿Calidad pidió separarlo?).
        this.state.rollNum = "";
        this.state.rollInfo = null;
        // Calidad al pesar: conforme (grado A) u observado (motivo + detalle).
        this.state.observed = false;
        this.state.observation = "";
        this.state.note = "";
        // Modo resolver: rollo observado que vuelve de reproceso + grado final.
        this.state.observedRolls = [];
        this.state.selectedObservedRoll = "";
        this.state.pendingGradeRolls = [];
        this.state.grade = "";
        this._rollInfoTimer = null;
        this.rollNumInputRef = useRef("rollNumInput");
        // Precarga las últimas partidas: al enfocar el buscador ya hay algo
        // que elegir sin teclear.
        onWillStart(() => this.searchBatches(""));
    }

    get isResolveMode() {
        return this.props.mode === "resolve";
    }

    get observationOptions() {
        return [
            { value: "stain", label: _t("Desmanchar") },
            { value: "decontaminate", label: _t("Descontaminar") },
            { value: "reprocess", label: _t("Reprocesar") },
            { value: "other", label: _t("Otro") },
        ];
    }

    _resetRollFields() {
        this.state.rollNum = "";
        this.state.rollInfo = null;
        this.state.observed = false;
        this.state.observation = "";
        this.state.note = "";
        this.state.selectedObservedRoll = "";
        this.state.grade = "";
    }

    // La balanza se recuerda por ESTACIÓN de pesado (clave global propia),
    // no por workorder como en el Taller.
    _getLSKey() {
        return "idtx_mrp.weigh_station";
    }

    // Sin workorder: se neutralizan las cargas de opciones/empleados/equipos
    // del padre (sus loaders notifican errores cuando no encuentran nada).
    async _loadOptions() {
        this.options = [];
    }
    async _hydrateOptions() {}
    async _syncResourcesFromOption() {}

    // Al reabrir el diálogo justo después de cerrarlo, el puerto COM puede
    // seguir liberándose: un reintento corto evita tener que reconectar a
    // mano (el permiso del puerto ya quedó otorgado en el navegador).
    async _autoConnectSerial() {
        await super._autoConnectSerial();
        if (!this.state.serialConnected) {
            await new Promise((resolve) => setTimeout(resolve, 600));
            await super._autoConnectSerial();
        }
    }

    // La estación pesa todo el día: al cerrar el diálogo se DETIENE la
    // lectura (se suelta el lector) pero el puerto NO se cierra — queda
    // abierto en la pestaña y el siguiente diálogo lo reutiliza al instante
    // vía _openSerialPort (port.readable se regenera tras cancel()). Cerrar
    // y reabrir el dispositivo de inmediato falla en Chrome/Linux por
    // timing del SO ("No se pudo abrir el puerto COM"). El navegador cierra
    // el puerto solo al cerrar la pestaña.
    async _stopSerial() {
        this._serialStop = true;
        this.state.serialConnected = false;
        try {
            if (this._serialReader) {
                await this._serialReader.cancel();
                try {
                    this._serialReader.releaseLock();
                } catch (e) {}
            }
        } catch (e) {}
        this._serialReader = null;
        this._serialPort = null;
    }

    // ---------------------------------------------------------------
    // Buscador de partida
    // ---------------------------------------------------------------
    async searchBatches(query) {
        const domain = [["state", "=", "batch"]];
        const term = (query || "").trim();
        if (term) {
            domain.push(["name", "ilike", term]);
        }
        this.state.isSearchingBatch = true;
        try {
            this.state.batches = await this.ormService.searchRead(
                "mrp.workorder.batch",
                domain,
                ["name", "color_name", "total_weight"],
                { order: "id desc", limit: 20 }
            );
        } catch {
            this.state.batches = [];
        } finally {
            this.state.isSearchingBatch = false;
        }
    }

    onBatchQueryInput(ev) {
        const value = ev.target.value || "";
        this.state.batchQuery = value;
        // Escribir invalida la partida ya elegida: se limpia todo lo que
        // dependía de ella (producto, rollo, N° de rollo...).
        if (this.state.selectedBatch) {
            this.clearBatch({ keepQuery: true });
        }
        this.state.showBatchDropdown = true;
        if (this._batchSearchTimer) {
            clearTimeout(this._batchSearchTimer);
        }
        this._batchSearchTimer = setTimeout(() => this.searchBatches(value), 250);
    }

    onBatchInputFocus() {
        if (!this.state.selectedBatch) {
            this.state.showBatchDropdown = true;
        }
    }

    clearBatch({ keepQuery = false } = {}) {
        this.state.selectedBatch = "";
        this.state.selectedBatchData = null;
        if (!keepQuery) {
            this.state.batchQuery = "";
            this.state.showBatchDropdown = false;
        }
        this.state.selectedProduct = "";
        this.state.products = [];
        this.state.rolls = [];
        this.state.selectedRoll = "";
        this.state.observedRolls = [];
        this._resetRollFields();
    }

    async selectBatch(batchId) {
        const batch = (this.state.batches || []).find((b) => `${b.id}` === `${batchId}`);
        this.state.selectedBatch = String(batchId);
        this.state.selectedBatchData = batch || null;
        this.state.batchQuery = batch?.name || "";
        this.state.showBatchDropdown = false;
        await this._applyBatchSelection();
    }

    async _applyBatchSelection() {
        this.state.selectedProduct = "";
        this.state.products = [];
        this.state.rolls = [];
        this.state.selectedRoll = "";
        this._resetRollFields();
        if (!this.state.selectedBatch) {
            return;
        }
        if (this.isResolveMode) {
            await this._loadObservedRolls();
            return;
        }
        const products = await this.ormService.call(
            "mrp.workorder.batch",
            "get_weighable_products",
            [[parseInt(this.state.selectedBatch)]]
        );
        this.state.products = products || [];
        if (this.state.products.length === 1) {
            this.state.selectedProduct = String(this.state.products[0].id);
            await this._loadRolls();
        }
        if (!this.state.products.length) {
            this.notification.add(
                _t("La partida no tiene rollos crudos (sin producto que pesar)."),
                { type: "danger" }
            );
        }
    }

    async onProductChange(ev) {
        this.state.selectedProduct = ev?.target?.value || "";
        await this._loadRolls();
    }

    async _loadRolls() {
        this.state.rolls = [];
        this.state.selectedRoll = "";
        if (!this.state.selectedBatch || !this.state.selectedProduct) {
            return;
        }
        const rolls = await this.ormService.call(
            "mrp.workorder.batch",
            "get_weighable_rolls",
            [[parseInt(this.state.selectedBatch)], parseInt(this.state.selectedProduct)]
        );
        this.state.rolls = rolls || [];
        if (this.state.rolls.length === 1) {
            this.state.selectedRoll = String(this.state.rolls[0].id);
        }
    }

    async _loadObservedRolls() {
        this.state.observedRolls = [];
        this.state.selectedObservedRoll = "";
        if (!this.state.selectedBatch) {
            return;
        }
        const rolls = await this.ormService.call(
            "mrp.workorder.batch",
            "get_reweigh_rolls",
            [[parseInt(this.state.selectedBatch)]]
        );
        this.state.observedRolls = rolls || [];
        if (this.state.observedRolls.length === 1) {
            this.state.selectedObservedRoll = String(this.state.observedRolls[0].id);
        }
        // Observados a los que Calidad aún no dio grado final: se muestran en
        // el diálogo para que quede claro qué falta y a quién le toca.
        this.state.pendingGradeRolls = await this.ormService.call(
            "mrp.workorder.batch",
            "get_observed_pending_grade",
            [[parseInt(this.state.selectedBatch)]]
        ) || [];
        if (!this.state.observedRolls.length && !this.state.pendingGradeRolls.length) {
            this.notification.add(
                _t("La partida no tiene rollos observados ni pendientes de repesar."),
                { type: "info" }
            );
        }
    }

    onRollNumInput(ev) {
        this.state.rollNum = ev?.target?.value || "";
        this.state.rollInfo = null;
        clearTimeout(this._rollInfoTimer);
        this._rollInfoTimer = setTimeout(() => this._refreshRollInfo(), 250);
    }

    async _refreshRollInfo() {
        const num = parseInt(this.state.rollNum);
        if (!this.state.selectedBatch || isNaN(num) || num <= 0) {
            this.state.rollInfo = null;
            return;
        }
        const info = await this.ormService.call(
            "mrp.workorder.batch",
            "get_roll_num_info",
            [[parseInt(this.state.selectedBatch)], num]
        );
        // Si el usuario siguió tecleando, descartar la respuesta vieja.
        if (parseInt(this.state.rollNum) !== num) {
            return;
        }
        this.state.rollInfo = info || null;
        if (info && info.hold && info.hold.observed && !info.weighed) {
            // Calidad pidió separar este rollo: se propone OBSERVADO con su motivo.
            this.state.observed = true;
            this.state.observation = info.hold.reason || "other";
            this.state.note = info.hold.note || "";
        }
    }

    // Grado que Calidad dio al N° de rollo antes del pesado (sin marca → A).
    get qualityGrade() {
        const hold = this.state.rollInfo && this.state.rollInfo.hold;
        if (hold && hold.observed) {
            return "";
        }
        return (hold && hold.grade) || "A";
    }

    // Calidad pidió SEPARAR este N° de rollo: Pesado no puede pesarlo como conforme.
    get isHoldObserved() {
        const hold = this.state.rollInfo && this.state.rollInfo.hold;
        return !!(hold && hold.observed && !this.isRollAlreadyWeighed);
    }

    setObserved(flag) {
        if (!flag && this.isHoldObserved) {
            this.notification.add(
                _t("Calidad pidió separar este rollo: se pesa como observado."),
                { type: "warning" }
            );
            return;
        }
        this.state.observed = !!flag;
        if (!flag) {
            this.state.observation = "";
            this.state.note = "";
        } else if (!this.state.observation) {
            this.state.observation = "stain";
        }
    }

    setGrade(grade) {
        this.state.grade = grade;
    }

    get isRollNumInvalid() {
        const num = parseInt(this.state.rollNum);
        return this.state.triedConfirm && (isNaN(num) || num <= 0);
    }

    get isRollAlreadyWeighed() {
        return !!(this.state.rollInfo && this.state.rollInfo.weighed);
    }

    // ------------------------------------------------------------------
    // Rearme por CERO: cada actualización del peso en vivo (polling IP o
    // trama serial) revisa si la balanza ya se descargó.
    // ------------------------------------------------------------------
    _checkZeroRearm() {
        if (!this.state.waitingZero) {
            return;
        }
        const w = parseFloat(this.state.manualWeight || "");
        if (!isNaN(w) && w <= this.constructor.ZERO_THRESHOLD) {
            this.state.waitingZero = false;
        }
    }

    _handleSerialLine(line) {
        super._handleSerialLine(line);
        this._checkZeroRearm();
    }

    async _pollScaleWeight() {
        await super._pollScaleWeight();
        this._checkZeroRearm();
    }

    async selectScale(scale) {
        this.state.waitingZero = false;
        await super.selectScale(scale);
    }

    async selectManual() {
        this.state.waitingZero = false;
        await super.selectManual();
    }

    get isWeighDisabled() {
        return this.state.weighing || (this.state.waitingZero &&
            (this.state.selectedMode === "scale" || this.state.selectedMode === "serial"));
    }

    get isBatchInvalid() {
        return this.state.triedConfirm && !this.state.selectedBatch;
    }

    get isProductInvalid() {
        return this.state.triedConfirm && !this.state.selectedProduct;
    }

    get isConfirmEnabled() {
        if (!this.state.selectedBatch) {
            return false;
        }
        if (this.isResolveMode) {
            if (!this.state.selectedObservedRoll) return false;
        } else {
            if (!this.state.selectedProduct) return false;
            const num = parseInt(this.state.rollNum);
            if (isNaN(num) || num <= 0 || this.isRollAlreadyWeighed) return false;
            if (this.state.observed && !this.state.observation) return false;
        }
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

    _getConfirmPayload(w) {
        return {
            scale_id: (this.state.selectedMode === "scale" || this.state.selectedMode === "serial")
                ? this.state.selectedScaleId : false,
            manual_weight: !isNaN(w) ? w : false,
            batch_id: this.state.selectedBatch,
            product_id: this.state.selectedProduct,
            print_sticker: this.state.printSticker,
            wo_roll_id: this.state.selectedRoll || false,
            mode: this.isResolveMode ? "resolve" : "weigh",
            roll_num: parseInt(this.state.rollNum) || false,
            observed: this.state.observed,
            observation: this.state.observed ? this.state.observation : false,
            note: this.state.note || false,
            roll_id: this.state.selectedObservedRoll || false,
            grade: this.state.grade || false,
        };
    }

    // Reemplaza al confirm() del padre: valida partida/producto en lugar de
    // opción/empleado/equipo; las validaciones de peso son las mismas.
    // El diálogo QUEDA ABIERTO para pesar el siguiente rollo (la balanza
    // sigue leyendo y el puerto COM permanece conectado); se cierra con el
    // botón Cerrar o tras un minuto de inactividad.
    async confirm() {
        if (this.isWeighDisabled) {
            this.notification.add(
                _t("Retira el rollo: el botón se reactiva cuando la balanza vuelva a 0."),
                { type: "warning" }
            );
            return;
        }
        this.state.triedConfirm = true;
        if (!this.state.selectedBatch) {
            this.notification.add(_t("Selecciona la partida."), { type: "danger" });
            return;
        }
        if (this.isResolveMode) {
            if (!this.state.selectedObservedRoll) {
                this.notification.add(_t("Selecciona el rollo a repesar."), { type: "danger" });
                return;
            }
        } else {
            if (!this.state.selectedProduct) {
                this.notification.add(_t("Selecciona el producto."), { type: "danger" });
                return;
            }
            const num = parseInt(this.state.rollNum);
            if (isNaN(num) || num <= 0) {
                this.notification.add(_t("Indica el N° de rollo (Acabado)."), { type: "danger" });
                return;
            }
            if (this.isRollAlreadyWeighed) {
                this.notification.add(
                    _t("Ese N° de rollo ya fue pesado. Si vuelve de reproceso usa 'Resolver observado'."),
                    { type: "danger" });
                return;
            }
            if (this.state.observed && !this.state.observation) {
                this.notification.add(_t("Indica el motivo de la observación."), { type: "danger" });
                return;
            }
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
        this._persistScaleSelection();
        // Reinicia el auto-cierre por inactividad y deja todo listo para el
        // siguiente rollo (NO se cierra ni se corta la lectura de peso).
        this._startAutoCloseTimer();
        this.state.triedConfirm = false;
        // Bloqueo INMEDIATO (antes del RPC): el pesado puede tardar unos
        // segundos (impresión del sticker) y el botón no debe aceptar otro
        // clic en ese lapso.
        this.state.weighing = true;
        try {
            const ok = await this.props.confirm(payload);
            // Pesado OK con balanza: bloquear Pesar hasta descargar (0).
            if (ok === true && (this.state.selectedMode === "scale" || this.state.selectedMode === "serial")) {
                this.state.waitingZero = true;
            }
            if (ok === true) {
                // Listo para el siguiente rollo: mismo lote/producto, nuevo N°.
                this._resetRollFields();
                if (this.isResolveMode) {
                    await this._loadObservedRolls();
                } else {
                    setTimeout(() => {
                        try {
                            if (this.rollNumInputRef?.el) {
                                this.rollNumInputRef.el.focus();
                            }
                        } catch (e) {}
                    }, 0);
                }
            }
        } finally {
            this.state.weighing = false;
            if (this.state.selectedMode === "manual") {
                this.state.manualWeight = "";
                setTimeout(() => {
                    try {
                        if (this.manualInputRef?.el) {
                            this.manualInputRef.el.focus();
                        }
                    } catch (e) {}
                }, 0);
            }
        }
    }

    closeDialog() {
        this.props.close();
    }
}
