/** @odoo-module */

import { SelectBatchDialog } from "./select_batch_dialog";

/**
 * Registro SIMPLE de partida para operaciones de tintorería SIN receta de
 * laboratorio (HABILITADO TELA TINTORERIA, HIDROEXTRACTORA, ...): un solo
 * paso — empleado, equipo y partida; las horas de inicio/fin ya viven en la
 * propia OT. Hereda del diálogo de teñido para reusar la carga de
 * empleados/equipos y el buscador de partidas (filtro por producto/color,
 * warnings, persistencia).
 */
export class SimpleBatchDialog extends SelectBatchDialog {
    static template = "idtx_mrp_shop.SimpleBatchDialog";

    setup() {
        super.setup();
        Object.assign(this.state, {
            triedConfirm: false,
        });
    }

    // La operación simple no usa datos de receta ni volúmenes:
    // anular los cálculos del flujo de teñido.
    async _maybeReloadDefaults() {}
    _computeVolumeValues() {}

    // =========================
    // Validación (campos en rojo, sin cerrar el diálogo)
    // =========================
    get isEmployeeInvalid() {
        return this.state.triedConfirm && !this.state.selectedEmployee;
    }

    get isEquipmentInvalid() {
        return this.state.triedConfirm && !this.state.selectedEquipment;
    }

    get isBatchInvalid() {
        return this.state.triedConfirm && !this.state.selectedBatchId;
    }

    confirm() {
        this.state.triedConfirm = true;
        if (!this.state.selectedEmployee || !this.state.selectedEquipment
            || !this.state.selectedBatchId) {
            return;
        }
        const payload = {
            batch_id: parseInt(this.state.selectedBatchId),
            employee_id: parseInt(this.state.selectedEmployee),
            equipment_id: parseInt(this.state.selectedEquipment),
        };
        this._persistPartial();
        this.props.confirm(payload);
        this.props.close();
    }
}
