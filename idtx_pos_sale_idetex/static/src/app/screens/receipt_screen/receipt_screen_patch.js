/** @odoo-module */

import { ReceiptScreen } from "@point_of_sale/app/screens/receipt_screen/receipt_screen";
import { patch } from "@web/core/utils/patch";
import { useState } from "@odoo/owl";
import OrderPaymentValidation from "@point_of_sale/app/utils/order_payment_validation";

patch(OrderPaymentValidation.prototype, {
    shouldDownloadInvoice() {
        return false;
    },

    // Se ejecuta automáticamente después de que el pago queda validado y el comprobante enviado.
    // Aprovechamos este gancho para actualizar el stock en memoria sin bloquear la pantalla de recibo.
    async afterOrderValidation() {
        const result = await super.afterOrderValidation(...arguments); // ejecutar lógica original primero
        this.pos.refreshStockData().catch(                             // actualizar stock en segundo plano
            e => console.error('IDTX: Stock refresh falló:', e)
        );
        return result;
    },
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
