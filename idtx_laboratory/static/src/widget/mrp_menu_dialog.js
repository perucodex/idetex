/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { MrpMenuDialog } from "@mrp_workorder/mrp_display/dialog/mrp_menu_dialog";
import { SelectScaleDialog } from "./select_scale_dialog";
import { SelectSizeDialog } from "./select_size_dialog";
import { _t } from "@web/core/l10n/translation";
import { useService } from "@web/core/utils/hooks";

patch(MrpMenuDialog.prototype, {

    setup() {
        super.setup();
        this.orm = useService("orm");
        this.notification = useService("notification");
        console.log("ID del Workorder:", this.props.record.data.id);
        console.log("Nombre:", this.props.record.data.name);
        console.log("Weave type:", this.props.record.data.weave_type);
        console.log("Quantity Producing:", this.props.record.data.qty_producing);
        console.log("State:", this.props.record.data.working_state);
    },

    readScaleWithClientIP() {
        const _selectScale = async (payload) => {
            const result = await this.orm.call("mrp.workorder", "action_read_scale", [
                [this.props.record.resId],
                payload.scale_id,
                payload.employee_id,
            ]);

            if (result) {
                this.notification.add(result.message, { type: result.status });
            }

            // refrescar el record
            this.props.record.save();
            this.props.removeFromCache(this.props.record.resId);
            this.props.close();
        };

        const params = {
            title: _t("Select a scale"),
            confirm: _selectScale,
            radioMode: true,
            scales: this.props.params.scales,
            employees: this.props.params.employees,
        };

        this.dialogService.add(SelectScaleDialog, params);
    },

    createSizeRecord() {
        const _createRecord = async (payload) => {
            const result = await this.orm.call(
                "mrp.workorder",
                "action_create_size_record",
                [[this.props.record.resId], payload.size, payload.quantity]
            );

            if (result) {
                this.notification.add(result.message, { type: result.status });
            }

            // refrescar el record
            await this.props.record.load();
            this.props.removeFromCache(this.props.record.resId);
            this.props.close();
        };

        const params = {
            title: _t("Select size and quantity"),
            confirm: _createRecord,
            recordId: this.props.record.resId,
        };

        this.dialogService.add(SelectSizeDialog, params);
    },

});
