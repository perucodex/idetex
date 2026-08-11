/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { listView } from "@web/views/list/list_view";
import { ListController } from "@web/views/list/list_controller";
import { WeighRollDialog } from "./weigh_roll_dialog";

/**
 * Pantalla "Pesado de rollos" (Manufactura → Operaciones): lista de rollos
 * terminados con un botón que abre el diálogo de balanza (partida + producto
 * + peso en vivo). Al confirmar, el backend crea rollo + lote
 * (partida-correlativo) + QUANT inmediato e imprime el sticker.
 */
export class RollWeighingListController extends ListController {
    setup() {
        super.setup();
        this.dialogService = useService("dialog");
        this.orm = useService("orm");
        this.notification = useService("notification");
    }

    openWeighDialog() {
        this.dialogService.add(WeighRollDialog, {
            title: _t("Pesar rollo"),
            confirm: async (payload) => {
                // Devuelve true/false: el diálogo bloquea el botón Pesar
                // hasta que la balanza vuelva a 0 SOLO si el pesado fue OK.
                try {
                    const res = await this.orm.call(
                        "mrp.workorder.batch",
                        "action_weigh_finished_roll",
                        [
                            [parseInt(payload.batch_id)],
                            parseInt(payload.product_id),
                            payload.scale_id || false,
                            payload.manual_weight,
                            payload.print_sticker !== false,
                            payload.wo_roll_id ? parseInt(payload.wo_roll_id) : false,
                        ]
                    );
                    if (res && res.status === "success") {
                        this.notification.add(res.message, { type: "success" });
                        return true;
                    }
                    this.notification.add((res && res.message) || _t("Error al pesar."), {
                        type: "danger",
                    });
                    return false;
                } finally {
                    await this.model.load();
                }
            },
        });
    }
}

registry.category("views").add("roll_weighing_list", {
    ...listView,
    Controller: RollWeighingListController,
    buttonTemplate: "idtx_mrp_shop.RollWeighingList.Buttons",
});
