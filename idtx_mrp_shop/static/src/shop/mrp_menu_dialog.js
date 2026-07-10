/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { MrpMenuDialog } from "@mrp_workorder/mrp_display/dialog/mrp_menu_dialog";
import { SelectScaleDialog } from "./select_scale_dialog";
import { SelectSizeDialog } from "./select_size_dialog";
import { SelectBatchDialog } from "./select_batch_dialog";
import { SimpleBatchDialog } from "./simple_batch_dialog";
import { _t } from "@web/core/l10n/translation";
import { useService } from "@web/core/utils/hooks";

patch(MrpMenuDialog.prototype, {

    setup() {
        super.setup();
        this.orm = useService("orm");
        this.notification = useService("notification");
    },

    async readScaleWithClientIP() {
        const _selectScale = async (payload) => {
            const result = await this.orm.call("mrp.workorder", "action_read_scale", [
                [this.props.record.resId],
                payload.scale_id,
                payload.employee_id,
                payload.equipment_id,
                payload.option_id,
                payload.manual_weight,
            ]);

            if (result) {
                this.notification.add(result.message, { type: result.status });
            }

            await this.props.record.load(); 
            this.props.removeFromCache(this.props.record.resId);
            this.props.close();
        };

        let roll_resIds = [];
        const roll_field = this.props.record.data.roll_ids;
        if (Array.isArray(roll_field)) {
            roll_resIds = roll_field;
        } else if (roll_field?.resIds) {
            roll_resIds = roll_field.resIds;
        }
        let defaultEmployee = "";
        let defaultEquipment = "";
        let defaultOption = "";
        if (roll_resIds && roll_resIds.length) {
            const rolls = await this.orm.searchRead(
                "mrp.workorder.roll",
                [["id", "in", roll_resIds]],
                ["employee_id", "equipment_id", "sequence", "option_id"]
            );
            if (rolls && rolls.length) {
                const lastRoll = rolls.reduce((a, b) => ( (a.sequence || 0) >= (b.sequence || 0) ? a : b ));
                if (lastRoll.employee_id) {
                    defaultEmployee = lastRoll.employee_id[0];
                }
                if (lastRoll.equipment_id) {
                    defaultEquipment = lastRoll.equipment_id[0];
                }
                if (lastRoll.option_id) {
                    defaultOption = lastRoll.option_id[0];
                }
            }
        };
        
        const params = {
            title: _t("Select a scale"),
            confirm: _selectScale,
            radioMode: true,
            scales: this.props.params.scales,
            selectedEmployee: defaultEmployee,
            selectedEquipment: defaultEquipment,
            selectedOption: defaultOption || "",
            active: [this.props.record.resId],
        };

        this.dialogService.add(SelectScaleDialog, params);
    },

    async createSizeRecord() {
        const _createRecord = async (payload) => {
            const result = await this.orm.call(
                "mrp.workorder",
                "action_create_size_record",
                [[this.props.record.resId],
                payload.size,
                payload.quantity,
                payload.employee_id,
                payload.equipment_id,
                payload.option_id,
                payload.manual_weight,
                payload.scale_id,
            ]);

            if (result) {
                this.notification.add(result.message, { type: result.status });
            }

            await this.props.record.load();
            this.props.removeFromCache(this.props.record.resId);
            this.props.close();
        };

        let roll_resIds = [];
        const roll_field = this.props.record.data.roll_ids;
        if (Array.isArray(roll_field)) {
            roll_resIds = roll_field;
        } else if (roll_field?.resIds) {
            roll_resIds = roll_field.resIds;
        }
        // Defaults desde el último roll (opción/empleado/equipo). El diálogo
        // carga las opciones del WO y filtra empleados/equipos por la opción
        // elegida (mismo patrón que select_scale_dialog).
        let defaultEmployee = "";
        let defaultEquipment = "";
        let defaultOption = "";
        let defaultSize = "";
        if (roll_resIds && roll_resIds.length) {
            const rolls = await this.orm.searchRead(
                "mrp.workorder.roll",
                [["id", "in", roll_resIds]],
                ["employee_id", "equipment_id", "option_id", "size_id", "sequence"]
            );
            if (rolls && rolls.length) {
                const lastRoll = rolls.reduce((a, b) => ( (a.sequence || 0) >= (b.sequence || 0) ? a : b ));
                if (lastRoll.employee_id) {
                    defaultEmployee = lastRoll.employee_id[0];
                }
                if (lastRoll.equipment_id) {
                    defaultEquipment = lastRoll.equipment_id[0];
                }
                if (lastRoll.option_id) {
                    defaultOption = lastRoll.option_id[0];
                }
                if (lastRoll.size_id) {
                    defaultSize = lastRoll.size_id[0];
                }
            }
        };

        const params = {
            title: _t("Select size and quantity"),
            confirm: _createRecord,
            // El diálogo hereda del de balanza: usa `active` para el workorder
            // (opciones, tallas, persistencia de selección).
            active: [this.props.record.resId],
            selectedEmployee: defaultEmployee || "",
            selectedEquipment: defaultEquipment || "",
            selectedOption: defaultOption || "",
            selectedSize: defaultSize || "",
        };

        this.dialogService.add(SelectSizeDialog, params);
    },

    async registerDyeBatch() {
        await new Promise(resolve => {
            const _createRecord = async (payload) => {
                const res = await this.orm.call(
                    "mrp.workorder",
                    "action_create_registry_record",
                    [[this.props.record.resId], payload]
                );

                if (res) {
                    this.notification.add(res.message, { type: res.status });
                }
                await this.props.record.load();
                this.props.removeFromCache(this.props.record.resId);

                resolve(res);
            };

            document.activeElement?.blur?.();
            this.dialogService.add(SelectBatchDialog, {
                title: _t("Select batch"),
                confirm: _createRecord,
                recordId: this.props.record.resId,
            });
        });

        this.props.close();
    },

    async registerBatchOperation() {
        // Operaciones de tintorería SIN receta de laboratorio (HABILITADO,
        // HIDROEXTRACTORA, ...): registro simple en un paso — partida + horas.
        await new Promise(resolve => {
            const _createRecord = async (payload) => {
                const res = await this.orm.call(
                    "mrp.workorder",
                    "action_register_batch_operation",
                    [[this.props.record.resId], payload]
                );

                if (res) {
                    this.notification.add(res.message, { type: res.status });
                }
                await this.props.record.load();
                this.props.removeFromCache(this.props.record.resId);

                resolve(res);
            };

            document.activeElement?.blur?.();
            this.dialogService.add(SimpleBatchDialog, {
                title: _t("Register batch operation"),
                confirm: _createRecord,
                recordId: this.props.record.resId,
            });
        });

        this.props.close();
    }

});



//     async openWorkOrder() {
//         const id = this.props.record.resId;

//         await this.action.doAction({
//             type: "ir.actions.act_window",
//             res_model: "mrp.workorder",
//             views: [[false, "form"]],
//             res_id: id,
//         });

//         this.props.close();
//     }

// });
