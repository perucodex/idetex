/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { onWillStart } from "@odoo/owl";
import { SelectScaleDialog } from "../shop/select_scale_dialog";

/**
 * Diálogo de PESADO DE ROLLOS TERMINADOS: hereda del diálogo de balanza del
 * Taller toda la lectura de peso (balanza por IP con polling, puerto COM por
 * Web Serial, manual con autorización, persistencia de balanza por estación)
 * y reemplaza Opción/Empleado/Equipo por Partida + Producto.
 */
export class WeighRollDialog extends SelectScaleDialog {
    static template = "idtx_mrp_shop.WeighRollDialog";
    static props = { ...SelectScaleDialog.props };

    // El botón Pesar se rearma cuando la balanza baja de este peso (kg):
    // evita registrar dos veces el mismo rollo sin haberlo retirado.
    static ZERO_THRESHOLD = 0.2;

    setup() {
        super.setup();
        this.state.batches = [];
        this.state.selectedBatch = "";
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
        onWillStart(async () => {
            const batches = await this.ormService.searchRead(
                "mrp.workorder.batch",
                [["state", "=", "batch"]],
                ["name"],
                { order: "id desc" }
            );
            this.state.batches = batches || [];
        });
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

    async onBatchChange(ev) {
        this.state.selectedBatch = ev?.target?.value || "";
        this.state.selectedProduct = "";
        this.state.products = [];
        this.state.rolls = [];
        this.state.selectedRoll = "";
        if (!this.state.selectedBatch) {
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
        if (!this.state.selectedBatch || !this.state.selectedProduct) {
            return false;
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
        if (!this.state.selectedProduct) {
            this.notification.add(_t("Selecciona el producto."), { type: "danger" });
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
