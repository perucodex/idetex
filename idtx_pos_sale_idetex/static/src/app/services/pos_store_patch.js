/** @odoo-module **/

import { PosStore } from "@point_of_sale/app/services/pos_store";
import { patch } from "@web/core/utils/patch";

patch(PosStore.prototype, {
    async setup() {
        await super.setup(...arguments);
        this.numpadMode = "price";
    },
    selectOrderLine(order, line) {
        super.selectOrderLine(...arguments);
        this.numpadMode = "price";
    }
});
