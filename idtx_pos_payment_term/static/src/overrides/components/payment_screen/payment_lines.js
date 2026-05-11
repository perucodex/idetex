import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";
import { PaymentScreenPaymentLines } from "@point_of_sale/app/screens/payment_screen/payment_lines/payment_lines";
import { PaymentTermPopup } from "@idtx_pos_payment_term/popups/payment_term_popup/payment_term_popup";
import { AlertDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { makeAwaitable } from "@point_of_sale/app/utils/make_awaitable_dialog";

patch(PaymentScreenPaymentLines.prototype, {
    async selectPaymentTerm(line) {
        const order = line.pos_order_id;
        const terms = this.pos.models["account.payment.term"].getAll();
        if (!terms.length) {
            this.dialog.add(AlertDialog, {
                title: _t("Sin terminos de pago"),
                body: _t(
                    "No hay terminos de pago disponibles. Configure al menos uno en Contabilidad."
                ),
            });
            return;
        }
        const selection = await makeAwaitable(this.dialog, PaymentTermPopup, {
            terms,
            selectedId: order.invoice_payment_term_id?.id || false,
        });
        if (selection) {
            order.invoice_payment_term_id = selection;
        }
    },
});
