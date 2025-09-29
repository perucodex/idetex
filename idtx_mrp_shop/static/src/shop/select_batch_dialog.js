/** @odoo-module */

import { _t } from "@web/core/l10n/translation";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { useService } from "@web/core/utils/hooks";
import { onWillStart, useState } from "@odoo/owl";

export class SelectBatchDialog extends ConfirmationDialog {

    static template = "idtx_mrp_shop.SelectBatchDialog";
    static props = {
        ...ConfirmationDialog.props,
        recordId: { type: Number, optional: true },
        batchs: { type: Array, optional: true },
        employees: { type: Array, optional: true },
        equipments: { type: Array, optional: true },
        selectedEmployee: { type: [Number, String], optional: true },   
        selectedEquipment: { type: [Number, String], optional: true },
    };

    setup() {
        super.setup();
        this.ormService = useService("orm");
        this.menu = useService("menu");
        this.notification = useService("notification");
        this.batchs = this.props.batchs || [];
        this.employees = this.props.employees || [];
        this.equipments = this.props.equipments || [];
        this.state = useState({
            batchs: [],
            selectedEmployee: "",
            selectedEquipment: "",
        });

        onWillStart(async () => {
            if (!this.batchs.length) {
                await this._loadBatchs();
            }
            if (!this.employees.length) {
                await this._loadEmployees();
            }
            if (!this.equipments.length) {
                await this._loadEquipments();
            }
        });
    }
    
    selectBatch(batch) {
        this.state.selectedBatchId = batch.id;
    }

    confirm() {
        if (!this.state.selectedBatchId) {
            this.notification.add(_t("You must select a batch."), { type: "danger" });
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
        const payload = {
            batch_id: this.state.selectedBatchId,
            employee_id: this.state.selectedEmployee || false,
            equipment_id: this.state.selectedEquipment || false,
        };
        this.props.confirm(payload);
        this.props.close();
    }

    async _loadEmployees() {
        const deptId = await this.ormService.searchRead(
            "ir.model.data",
            [['name', '=', 'tintoreria'], ['module', '=', 'idtx_mrp_shop']],
            ['res_id']
        ).then(data => data[0]?.res_id || false);

        if (!deptId) {
            this.notification.add(
                _t("Department 'Tintorería' not found. Please check the external ID."),
                { type: "danger" }
            );
            return;
        }

        this.employees = await this.ormService.searchRead("hr.employee", [['department_id','=',deptId]], ["name"]);
        if (!this.employees.length) {
            this.notification.add(
                _t("No employees are available, please assign one first to add it to the shop floor view"),
                { type: "danger" }
            );
        }
    }

    async _loadBatchs() {
        this.batchs = await this.ormService.searchRead("mrp.workorder.batch", [['state','=','batch']], ["id","name"]);
        if (!this.batchs.length) {
            this.notification.add(
                _t("No batchs are available, please create one first to add it to the shop floor view"),
                { type: "danger" }
            );
        }
    }

    async _loadEquipments() {
        const workcenterId = await this.ormService.searchRead(
            "ir.model.data",
            [['name', '=', 'mrp_wc_2'], ['module', '=', 'idtx_mrp']],
            ['res_id']
        ).then(data => data[0]?.res_id || false);

        if (!workcenterId) {
            this.notification.add(
                _t("Workcenter_id 'Tintorería' not found. Please check the external ID."),
                { type: "danger" }
            );
            return;
        }

        this.equipments = await this.ormService.searchRead("maintenance.equipment", [['workcenter_id','in',workcenterId]], ["name"]);
        if (!this.equipments.length) {
            this.notification.add(
                _t("No equipments are available, please assign one first to add it to the shop floor view"),
                { type: "danger" }
            );
        }
    }

}
