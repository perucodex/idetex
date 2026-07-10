/** @odoo-module */

import { SelectBatchDialog } from "./select_batch_dialog";
import { deserializeDateTime, serializeDateTime } from "@web/core/l10n/dates";
import { onWillStart } from "@odoo/owl";

const { DateTime } = luxon;

/**
 * Registro SIMPLE de partida para operaciones de tintorería SIN receta de
 * laboratorio (HABILITADO TELA TINTORERIA, HIDROEXTRACTORA, ...): un solo
 * paso — elegir la partida y registrar a qué hora empezó y terminó la
 * operación. Hereda del diálogo de teñido para reusar el buscador de
 * partidas (filtro por producto/color, warnings, persistencia).
 */
export class SimpleBatchDialog extends SelectBatchDialog {
    static template = "idtx_mrp_shop.SimpleBatchDialog";

    setup() {
        super.setup();
        Object.assign(this.state, {
            dateStart: "",
            dateEnd: DateTime.now().toFormat("yyyy-MM-dd'T'HH:mm"),
            triedConfirm: false,
        });

        onWillStart(async () => {
            // Precargar el inicio con el INICIAR real de la OT.
            if (this.state.workorderId && !this.state.dateStart) {
                try {
                    const wo = await this.ormService.read(
                        "mrp.workorder", [this.state.workorderId], ["date_start"]
                    );
                    const ds = wo[0]?.date_start;
                    if (ds) {
                        this.state.dateStart = deserializeDateTime(ds).toFormat("yyyy-MM-dd'T'HH:mm");
                    }
                } catch (e) {
                    // sin default, el operador lo digita
                }
            }
        });
    }

    // La operación simple no pide empleado/equipo ni datos de receta:
    // anular las cargas y cálculos del flujo de teñido.
    async _loadEmployees() {}
    async _loadEquipments() {}
    async _maybeReloadDefaults() {}
    _computeVolumeValues() {}

    onDateInput(ev, fieldName) {
        this.state[fieldName] = ev?.target?.value || "";
    }

    // =========================
    // Validación (campos en rojo, sin cerrar el diálogo)
    // =========================
    get isRangeInvalid() {
        return !!(this.state.dateStart && this.state.dateEnd
            && this.state.dateEnd < this.state.dateStart);
    }

    get isBatchInvalid() {
        return this.state.triedConfirm && !this.state.selectedBatchId;
    }

    get isStartInvalid() {
        return this.state.triedConfirm && (!this.state.dateStart || this.isRangeInvalid);
    }

    get isEndInvalid() {
        return this.state.triedConfirm && (!this.state.dateEnd || this.isRangeInvalid);
    }

    confirm() {
        this.state.triedConfirm = true;
        if (!this.state.selectedBatchId || !this.state.dateStart
            || !this.state.dateEnd || this.isRangeInvalid) {
            return;
        }
        const payload = {
            batch_id: parseInt(this.state.selectedBatchId),
            date_start: serializeDateTime(DateTime.fromISO(this.state.dateStart)),
            date_end: serializeDateTime(DateTime.fromISO(this.state.dateEnd)),
        };
        this._persistPartial();
        this.props.confirm(payload);
        this.props.close();
    }
}
