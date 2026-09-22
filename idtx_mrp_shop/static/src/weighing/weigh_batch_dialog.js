/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { onWillStart } from "@odoo/owl";
import { SelectScaleDialog } from "../shop/select_scale_dialog";

/**
 * CONTROL DE PESO de la partida (operación de la ruta marcada "Control de
 * peso", JP 22-sep-2026): hereda del diálogo de balanza del Taller (opción,
 * empleado, equipo, balanza IP/COM, manual autorizado, persistencia por OT) y
 * agrega el buscador de partida. El peso confirmado queda en la partida como
 * "Peso tras control" y es el que usa la receta de teñido.
 */
export class WeighBatchDialog extends SelectScaleDialog {
    static template = "idtx_mrp_shop.WeighBatchDialog";

    setup() {
        super.setup();
        // Partida: buscador con autocompletado (en planta hay cientos abiertas).
        this.state.batches = [];
        this.state.selectedBatch = "";
        this.state.selectedBatchData = null;
        this.state.batchQuery = "";
        this.state.showBatchDropdown = false;
        this.state.isSearchingBatch = false;
        this._batchSearchTimer = null;
        // Precarga las últimas partidas para elegir sin teclear.
        onWillStart(() => this.searchBatches(""));
    }

    // El control de peso no usa opciones de la OT ni máquinas: se anulan los
    // cargadores del padre (avisaban "sin opciones" / "sin equipos" al abrir).
    // Los empleados sí se cargan (todos, como en el resto del Taller).
    async _loadOptions() {
        this.options = [];
    }

    async _hydrateOptions() {}

    async _loadEquipments() {
        this.state.equipments = [];
    }

    // ---------------------------------------------------------------
    // Partida
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
                ["display_name", "color_name", "total_weight", "controlled_weight", "recipe_weight"],
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
    }

    selectBatch(batchId) {
        const batch = (this.state.batches || []).find((b) => `${b.id}` === `${batchId}`);
        this.state.selectedBatch = batch ? String(batch.id) : "";
        this.state.selectedBatchData = batch || null;
        this.state.batchQuery = batch ? batch.display_name : "";
        this.state.showBatchDropdown = false;
    }

    get isBatchInvalid() {
        return this.state.triedConfirm && !this.state.selectedBatch;
    }

    // ---------------------------------------------------------------
    // Confirmación: solo EMPLEADO y PARTIDA (el control de peso no lleva
    // máquina) + las mismas validaciones de peso del diálogo de balanza.
    // ---------------------------------------------------------------
    get isEquipmentInvalid() {
        return false;
    }

    get isConfirmEnabled() {
        if (!this.state.selectedEmployee || !this.state.selectedBatch) return false;
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
            batch_id: parseInt(this.state.selectedBatch),
            employee_id: parseInt(this.state.selectedEmployee),
            equipment_id: this.state.selectedEquipment ? parseInt(this.state.selectedEquipment) : false,
            scale_id: (this.state.selectedMode === "scale" || this.state.selectedMode === "serial")
                ? this.state.selectedScaleId : false,
            manual_weight: !isNaN(w) ? w : false,
        };
    }

    async confirm() {
        // Anti doble clic (igual que el padre).
        if (this._isConfirmed) {
            return;
        }
        this.state.triedConfirm = true;
        if ((this.options || []).length > 0 && !this.state.selectedOption) {
            this.notification.add(_t("You must select an option."), { type: "danger" });
            return;
        }
        if (!this.state.selectedEmployee) {
            this.notification.add(_t("You must select an employee."), { type: "danger" });
            return;
        }
        if (!this.state.selectedBatch) {
            this.notification.add(_t("Debes seleccionar la partida a pesar."), { type: "danger" });
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
        this._persistSelectionPartial({ includeEmpty: true });
        this._persistScaleSelection();
        this._isConfirmed = true;
        this._clearAutoCloseTimer();
        this._stopScalePolling();
        // Se espera al servidor antes de cerrar (ver diálogo padre).
        try {
            await this.props.confirm(payload);
        } finally {
            this.props.close();
        }
    }
}
