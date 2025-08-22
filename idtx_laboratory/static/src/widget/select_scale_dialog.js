/** @odoo-module */

import { _t } from "@web/core/l10n/translation";
import { isDisplayStandalone } from "@web/core/browser/feature_detection";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { useService } from "@web/core/utils/hooks";
import { onWillStart, useState } from "@odoo/owl";

export class SelectScaleDialog extends ConfirmationDialog {

    static template = "idtx_laboratory.SelectScaleDialog";
    static props = {
        ...ConfirmationDialog.props,
        body: { type: String, optional: true },
        scales: { type: Array, optional: true },
        employees: { type: Array, optional: true },
        disabled: { type: Array, optional: true },
        active: { type: Array, optional: true },
        radioMode: { type: Boolean, default: false, optional: true },
        showWarning: { type: Boolean, default: false, optional: true },
    };

    setup() {
        super.setup();
        this.ormService = useService("orm");
        this.menu = useService("menu");
        this.notification = useService("notification");
        this.scales = this.props.scales || [];
        this.employees = this.props.employees || [];
        this.state = useState({
            activeScales: this.props.active ? [...this.props.active] : [],
            selectedEmployee: "", 
        });
        this.isDisplayStandalone = isDisplayStandalone();

        onWillStart(async () => {
            if (!this.scales.length) {
                await this._loadScales();
            }
            if (!this.employees.length) {
                await this._loadEmployees();
            }
        });
    }

    get appName() {
        return encodeURIComponent(this.menu.getCurrentApp().name);
    }

    get active() {
        return this.state.activeScales.includes(this.scale.id);
    }

    get disabled() {
        if (!this.props.disabled) {
            return false;
        }
        return this.props.disabled.includes(this.scale.id);
    }

    selectScale(scale) {
        if (this.props) {
            this.state.activeScales = [scale.id];
        } else if (this.state.activeScales.includes(scale.id)) {
            this.state.activeScales = this.state.activeScales.filter(
                (id) => id !== scale.id
            );
        } else {
            this.state.activeScales.push(scale.id);
        }
    }

    confirm() {
        const payload = {
            scale_id: this.state.activeScales[0] || false,
            employee_id: this.state.selectedEmployee || false,
        };
        this.props.confirm(payload);
        this.props.close();
    }

    async _loadScales() {
        this.scales = await this.ormService.searchRead("scale.registry", [], ["name"]);
        if (!this.scales.length) {
            this.notification.add(
                _t("No scales are available, please create one first to add it to the shop floor view"),
                { type: "danger" }
            );
        }
    }

    async _loadEmployees() {
        const employee_ids = this.props.record.data.employee_assigned_ids || [];
        this.employees = await this.ormService.searchRead("hr.employee", [['id','in',employee_ids]], ["name"]);
        if (!this.employees.length) {
            this.notification.add(
                _t("No employees are available, please assign one first to add it to the shop floor view"),
                { type: "danger" }
            );
        }
    }
}
