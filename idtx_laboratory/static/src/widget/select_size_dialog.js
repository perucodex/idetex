/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { useService } from "@web/core/utils/hooks";
import { onWillStart, useState } from "@odoo/owl";

export class SelectSizeDialog extends ConfirmationDialog {
    static template = "idtx_laboratory.SelectSizeDialog";
    static props = {
        ...ConfirmationDialog.props,
        sizes: { type: Array, optional: true },
        recordId: { type: Number },
        employees: { type: Array, optional: true },
        equipments: { type: Array, optional: true },
        selectedEmployee: { type: [Number, String], optional: true },
        selectedEquipment: { type: [Number, String], optional: true },
    };

    setup() {
        super.setup();
        this.ormService = useService("orm");
        this.notification = useService("notification");
        this.sizes = this.props.sizes || [];
        this.employees = this.props.employees || [];
        this.equipments = this.props.equipments || [];
        this.state = useState({
            quantity: 1,
            sizes: this.sizes || [],
            selectedSize: null,
            selectedEmployee: this.props.selectedEmployee || "",
            selectedEquipment: this.props.selectedEquipment || "",
        });
        onWillStart(async () => {
            if (!this.state.sizes.length) {
                await this._loadSizes();
            }
            if (!this.employees.length) {
                await this._loadEmployees();
            }
            if (!this.equipments.length) {
                await this._loadEquipments();
            }
        });
    }

    selectSize(size) {
        this.state.selectedSize = size;
    }

    confirm() {
        if (this.state.selectedSize && this.state.quantity > 0) {
            this.props.confirm({
                size: this.state.selectedSize,
                quantity: this.state.quantity,
                employee_id: this.state.selectedEmployee || false,
                equipment_id: this.state.selectedEquipment || false,
            });
        } else {
            this.notification.add(_t("You must select a size and quantity."), { type: "danger" });
            return;
        }
        this.props.close();
    }

    async _loadSizes() {
        // Llamar al ORM para leer las tallas desde el workorder
        const result = await this.ormService.call(
            "mrp.workorder",
            "get_available_sizes",
            [this.props.recordId]
        );
        this.state.sizes = result;
        if (!this.state.sizes.length) {
            this.notification.add(
                _t("No sizes on technical sheet of the product."),
                { type: "danger" }
            );
        }
    }

    async _loadEmployees() {
        const employee_ids = this.props.employee_ids || [];
        this.employees = await this.ormService.searchRead("hr.employee", [['id','in',employee_ids]], ["name"]);
        if (!this.employees.length) {
            this.notification.add(
                _t("No employees are available, please assign one first to add it to the shop floor view"),
                { type: "danger" }
            );
        }
    }

    async _loadEquipments() {
        const equipment_ids = this.props.equipment_ids || [];
        this.equipments = await this.ormService.searchRead("maintenance.equipment", [['id','in',equipment_ids]], ["name"]);
        if (!this.equipments.length) {
            this.notification.add(
                _t("No equipments are available, please assign one first to add it to the shop floor view"),
                { type: "danger" }
            );
        }
    }
}
