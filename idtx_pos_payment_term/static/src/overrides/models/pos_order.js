import { patch } from "@web/core/utils/patch";
import { PosOrder } from "@point_of_sale/app/models/pos_order";

patch(PosOrder.prototype, {
    removePaymentline(line) {
        const removedUsesTerms = line.payment_method_id?.use_payment_terms;
        super.removePaymentline(line);
        if (
            removedUsesTerms &&
            !this.payment_ids.some((p) => p.payment_method_id?.use_payment_terms)
        ) {
            this.invoice_payment_term_id = false;
        }
    },
});
