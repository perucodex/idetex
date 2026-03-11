/** @odoo-module */

import { ReceiptScreen } from "@point_of_sale/app/screens/receipt_screen/receipt_screen";
import { patch } from "@web/core/utils/patch";
import { useState } from "@odoo/owl";

patch(ReceiptScreen.prototype, {
    setup() {
        super.setup(...arguments);
        // Estado para controlar si imprimimos detallado o agrupado
        this.receiptState = useState({
            printDetailed: false,
        });
    },

    togglePrintDetailed() {
        this.receiptState.printDetailed = !this.receiptState.printDetailed;
    }
});
