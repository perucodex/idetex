/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { useService } from "@web/core/utils/hooks";
import { useState } from "@odoo/owl";

export class SelectSizeDialog extends ConfirmationDialog {
    static template = "idtx_laboratory.SelectSizeDialog";
    static props = {
        ...ConfirmationDialog.props,
        sizes: { type: Array, optional: true },
        recordId: { type: Number }, // el workorder ID
    };

    setup() {
        super.setup();
        this.ormService = useService("orm");
        this.notification = useService("notification");
        this.state = useState({
            selectedSize: null,
            quantity: 1,
            sizes: this.props.sizes || [],
        });
        if (!this.props.sizes || !this.props.sizes.length) {
            this._loadSizes();
        } 
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

    selectSize(size) {
        this.state.selectedSize = size;
    }

    confirm() {
        if (this.state.selectedSize && this.state.quantity > 0) {
            this.props.confirm({
                size: this.state.selectedSize,
                quantity: this.state.quantity,
            });
        } else {
            this.notification.add(_t("You must select a size and quantity."), { type: "danger" });
            return;
        }
        this.props.close();
    }
}
