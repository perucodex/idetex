/** @odoo-module **/
/**
 * FIX defensivo para PaymentScreen.onMounted del core Odoo 19.
 *
 * Bug del core (odoo/addons/point_of_sale/.../payment_screen.js:79):
 *   if (this.currentOrder.isRefund &&
 *       this.currentOrder.lines[0].refunded_orderline_id?.order_id?.isToInvoice())
 *
 * El acceso a `lines[0]` falla con TypeError cuando una orden marcada como
 * refund quedó sin líneas (estado inconsistente que puede ocurrir tras
 * devoluciones parciales o cancelaciones a mitad de flujo). Esto rompe el
 * render del PaymentScreen y bloquea el POS al ir a "Pagar".
 *
 * Solución: reemplazamos onMounted con la misma lógica pero verificando que
 * lines tenga al menos 1 elemento antes de leer lines[0].
 */
import { PaymentScreen } from "@point_of_sale/app/screens/payment_screen/payment_screen";
import { patch } from "@web/core/utils/patch";

patch(PaymentScreen.prototype, {
    onMounted() {
        const order = this.pos.getOrder();

        // Limpiar payment_ids con métodos que no están en la config actual
        for (const payment of order.payment_ids) {
            const pmid = payment.payment_method_id.id;
            if (!this.pos.config.payment_method_ids.map((pm) => pm.id).includes(pmid)) {
                payment.delete({ backend: true });
            }
        }

        // Auto-seleccionar método de pago si solo hay uno configurado
        if (this.payment_methods_from_config.length == 1 && this.paymentLines.length == 0) {
            this.addNewPaymentLine(this.payment_methods_from_config[0]);
        }

        // Lógica de facturación automática para devoluciones:
        //   - Si la venta original tenía comprobante  → forzar a FACTURAR (genera NC)
        //   - Si la venta original NO tenía comprobante → forzar a NO FACTURAR
        //     (evita que el cajero marque por error y se intente generar NC sin
        //      documento original que la respalde).
        //
        // FIX vs core Odoo: el core solo hace el primer caso. Nosotros agregamos
        // el segundo para que las devoluciones de ventas sin comprobante queden
        // explícitamente bloqueadas (combinado con el XML que deshabilita el botón).
        //
        // FIX adicional: verificamos lines.length > 0 antes de leer lines[0] para
        // evitar TypeError cuando un refund queda huérfano sin líneas (bug del core).
        if (this.currentOrder.isRefund) {
            const originalIsToInvoice =
                this.currentOrder.lines.length > 0 &&
                this.currentOrder.lines[0].refunded_orderline_id?.order_id?.isToInvoice();

            if (originalIsToInvoice) {
                // Caso 1: original con comprobante → forzar facturación de la devolución
                this.currentOrder.setToInvoice(true);
            } else {
                // Caso 2: original sin comprobante → forzar NO facturación
                this.currentOrder.setToInvoice(false);
            }
        }
    },
});
