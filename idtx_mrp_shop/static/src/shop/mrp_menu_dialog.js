/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { MrpMenuDialog } from "@mrp_workorder/mrp_display/dialog/mrp_menu_dialog";
import { SelectScaleDialog } from "./select_scale_dialog";
import { SelectSizeDialog } from "./select_size_dialog";
import { SelectBatchDialog } from "./select_batch_dialog";
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
        let defaultEmployee = this.props.record.data.employee_assigned_ids?.resIds?.[0] || "";
        let defaultEquipment = this.props.record.data.equipment_ids?.resIds?.[0] || "";
        if (roll_resIds && roll_resIds.length) {
            const rolls = await this.orm.searchRead(
                "mrp.workorder.roll",
                [["id", "in", roll_resIds]],
                ["employee_id", "equipment_id", "sequence"]
            );
            if (rolls && rolls.length) {
                const lastRoll = rolls.reduce((a, b) => ( (a.sequence || 0) >= (b.sequence || 0) ? a : b ));
                if (lastRoll.employee_id) {
                    defaultEmployee = lastRoll.employee_id[0];
                }
                if (lastRoll.equipment_id) {
                    defaultEquipment = lastRoll.equipment_id[0];
                }
            }
        };
        
        const params = {
            title: _t("Select a scale"),
            confirm: _selectScale,
            radioMode: true,
            scales: this.props.params.scales,
            employee_ids: this.props.record.data.employee_assigned_ids.resIds,
            equipment_ids: this.props.record.data.equipment_ids.resIds,
            selectedEmployee: defaultEmployee,
            selectedEquipment: defaultEquipment,
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
        let defaultEmployee = this.props.record.data.employee_assigned_ids?.resIds?.[0] || "";
        let defaultEquipment = this.props.record.data.equipment_ids?.resIds?.[0] || "";
        if (roll_resIds && roll_resIds.length) {
            const rolls = await this.orm.searchRead(
                "mrp.workorder.roll",
                [["id", "in", roll_resIds]],
                ["employee_id", "equipment_id", "sequence"]
            );
            if (rolls && rolls.length) {
                const lastRoll = rolls.reduce((a, b) => ( (a.sequence || 0) >= (b.sequence || 0) ? a : b ));
                if (lastRoll.employee_id) {
                    defaultEmployee = lastRoll.employee_id[0];
                }
                if (lastRoll.equipment_id) {
                    defaultEquipment = lastRoll.equipment_id[0];
                }
            }
        };

        const params = {
            title: _t("Select size and quantity"),
            confirm: _createRecord,
            recordId: this.props.record.resId,
            employee_ids: this.props.record.data.employee_assigned_ids.resIds,
            equipment_ids: this.props.record.data.equipment_ids.resIds,
            selectedEmployee: defaultEmployee || "",
            selectedEquipment: defaultEquipment || "",
        };

        this.dialogService.add(SelectSizeDialog, params);
    },

    async registerDyeBatch() {
        const _createRecord = async (payload) => {
            const result = await this.orm.call(
                "mrp.workorder",
                "action_create_registry_record",
                [[this.props.record.resId], 
                payload.batch_id,
            ]);

            if (result) {
                this.notification.add(result.message, { type: result.status });
            }

            await this.props.record.load();
            this.props.removeFromCache(this.props.record.resId);

            await this.action.doAction({
                type: "ir.actions.act_window",
                res_model: "batch.registry",
                views: [[false, "form"]],
                res_id: result,
            });

            this.props.close();
        };

        const params = {
            title: _t("Select batch"),
            confirm: _createRecord,
            recordId: this.props.record.resId,
        };

        this.dialogService.add(SelectBatchDialog, params);
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
