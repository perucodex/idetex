import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";
import { PaymentScreen } from "@point_of_sale/app/screens/payment_screen/payment_screen";
import { PaymentTermPopup } from "@idtx_pos_payment_term/popups/payment_term_popup/payment_term_popup";
import { AlertDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { makeAwaitable } from "@point_of_sale/app/utils/make_awaitable_dialog";

patch(PaymentScreen.prototype, {
    async addNewPaymentLine(paymentMethod) {
        if (paymentMethod.use_payment_terms) {
            const term = await this._askPaymentTerm();
            if (!term) {
                return false;
            }
            this.currentOrder.invoice_payment_term_id = term;
            if (this.pos.config.canInvoice) {
                this.currentOrder.setToInvoice(true);
            }
        }
        return await super.addNewPaymentLine(paymentMethod);
    },

    async _askPaymentTerm() {
        const terms = this.pos.models["account.payment.term"].getAll();
        if (!terms.length) {
            this.dialog.add(AlertDialog, {
                title: _t("Sin terminos de pago"),
                body: _t(
                    "No hay terminos de pago disponibles. Configure al menos uno en Contabilidad."
                ),
            });
            return null;
        }
        const selection = await makeAwaitable(this.dialog, PaymentTermPopup, {
            terms,
            selectedId: this.currentOrder.invoice_payment_term_id?.id || false,
        });
        return selection || null;
    },
});
