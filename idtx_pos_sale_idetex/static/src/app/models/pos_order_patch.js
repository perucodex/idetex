/** @odoo-module **/
/**
 * Patch del modelo pos.order del POS frontend para BLOQUEAR la activación
 * de `to_invoice=true` en devoluciones cuya VENTA ORIGINAL no tenía comprobante.
 *
 * Contexto del problema:
 *   El core de Odoo (pos_order.js → setPartner) hace:
 *       if (partner.is_company) { this.setToInvoice(true); }
 *   Cuando una devolución hereda el partner de la venta original y ese partner
 *   es una empresa (RUC), automáticamente se marca `to_invoice=true` aunque la
 *   venta original NO haya tenido comprobante. Resultado: se genera una NC
 *   sin documento original que la respalde — comportamiento incorrecto para
 *   Idetex (no se debe enviar nada a SUNAT en ese caso).
 *
 *   Mi patch anterior en payment_screen_patch.js (onMounted con setToInvoice(false))
 *   se ejecuta antes que `setPartner` en la cadena de inicialización del refund,
 *   por lo que se sobrescribe.
 *
 * Solución:
 *   Patch del método `setToInvoice` para que en órdenes refund verifique el
 *   estado de la VENTA ORIGINAL. Si esa venta no tenía comprobante, ignora
 *   cualquier intento de setear `true` y fuerza `false`. Funciona sin importar
 *   QUIÉN llame a setToInvoice (setPartner, addNewPaymentLine, etc).
 */
import { PosOrder } from "@point_of_sale/app/models/pos_order";
import { patch } from "@web/core/utils/patch";

patch(PosOrder.prototype, {
    /** @override */
    setToInvoice(to_invoice) {
        // Solo bloqueamos cuando alguien intenta ACTIVAR la facturación (true).
        // Las llamadas con false siempre pasan.
        if (to_invoice === true && this.isRefund) {
            // Verificar si la venta original tenía comprobante. Si no, FORZAR false.
            const originalHadInvoice =
                this.lines.length > 0 &&
                this.lines[0].refunded_orderline_id?.order_id?.isToInvoice();

            if (!originalHadInvoice) {
                // Refund de venta sin comprobante → ignorar el intento de activar
                // facturación y forzar false. Log para diagnóstico.
                console.info(
                    "[IDTX] Bloqueado setToInvoice(true) en refund de venta sin comprobante"
                );
                return super.setToInvoice(false);
            }
        }
        return super.setToInvoice(to_invoice);
    },
});
