/** @odoo-module */

import { ReceiptScreen } from "@point_of_sale/app/screens/receipt_screen/receipt_screen";
import { patch } from "@web/core/utils/patch";
import { useState } from "@odoo/owl";
import OrderPaymentValidation from "@point_of_sale/app/utils/order_payment_validation";

patch(OrderPaymentValidation.prototype, {
    shouldDownloadInvoice() {
        return false;
    }
});

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
    },

    async printInvoice() {
        const accountMoveId = this.currentOrder.raw.account_move;
        if (accountMoveId) {
            await this.pos.env.services.account_move.downloadPdf(accountMoveId);
        }
    }
});
