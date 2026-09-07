/** @odoo-module **/
/**
 * REGLA SUNAT: tope de S/ 700 para BOLETA al "Consumidor Final".
 *
 * Contexto (pedido del usuario 2026-08-10): el "Cliente genérico" del POS es
 * el partner nativo "Consumidor Final" (l10n_pe_pos.partner_pe_cf, DNI,
 * VAT "00000000"). Al ser un cliente sin RUC, todo comprobante que se le emite
 * es BOLETA. SUNAT no permite emitir una boleta a consumidor final anónimo por
 * más de S/ 700; por encima de ese monto hay que identificar al comprador
 * (cambiarlo por un cliente real con DNI o RUC).
 *
 * Comportamiento: si el pedido es para el Consumidor Final y su total con
 * impuestos supera S/ 700, se BLOQUEA la validación del pago (return false),
 * se muestra un aviso y, al cerrarlo, se abre la selección de cliente para que
 * el cajero elija uno identificado.
 *
 * Punto de enganche: OrderPaymentValidation.isOrderValid — el mismo gancho que
 * usa la localización peruana (l10n_pe_pos) para exigir VAT. Devolver false
 * impide continuar con la validación del pedido.
 */
// Helper de validación del pago del POS (define isOrderValid, el "gate" real).
import OrderPaymentValidation from "@point_of_sale/app/utils/order_payment_validation";
// Utilidad para extender/parchear prototipos sin tocar el core.
import { patch } from "@web/core/utils/patch";
// Traducción de textos visibles al usuario.
import { _t } from "@web/core/l10n/translation";
// Diálogo de alerta (un solo botón) reutilizado del core web.
import { AlertDialog } from "@web/core/confirmation_dialog/confirmation_dialog";

// Tope máximo (en soles) de una boleta al Consumidor Final anónimo.
const TOPE_BOLETA_CF = 700;

patch(OrderPaymentValidation.prototype, {
    async isOrderValid(isForceValidate) {
        // Primero respetamos toda la validación previa (core + otros patches).
        const res = await super.isOrderValid(...arguments);
        // Si ya venía inválida, no seguimos evaluando nuestra regla.
        if (!res) {
            return false;
        }
        // ALCANCE: la regla es EXCLUSIVA de la caja IDETEX (el POS de la tienda).
        // Cualquier otra caja —Orden Pima, Orden Franela, FULL PIMA u otra
        // empresa— queda fuera. Se identifica por el nombre de la caja
        // (config.name contiene "IDETEX"), estable en clon, staging y prod.
        // Si algún día se renombra la caja, actualizar este criterio.
        const nombreCaja = (this.pos.config.name || "").toUpperCase();
        if (!nombreCaja.includes("IDETEX")) {
            return res;
        }
        // La regla aplica solo cuando se EMITIRÁ un comprobante (boleta):
        // "Recibo/Factura" marcado (isToInvoice). En ventas SIN comprobante no
        // se emite boleta, así que el tope SUNAT de S/700 no corresponde.
        if (!this.order.isToInvoice || !this.order.isToInvoice()) {
            return res;
        }
        // Cliente actual del pedido.
        const partner = this.order.getPartner();
        // Sin cliente asignado no hay Consumidor Final que validar.
        if (!partner) {
            return res;
        }
        // Id del partner "Consumidor Final" que el POS carga en su config.
        const cfId = this.pos.config._consumidor_final_anonimo_id;
        // Detectamos al Consumidor Final por id (principal) y, como refuerzo,
        // por su VAT genérico "00000000" (por si se usa otro partner anónimo).
        const esConsumidorFinal =
            (cfId && partner.id === cfId) || partner.vat === "00000000";
        // Si no es el Consumidor Final, la venta puede ser factura o boleta a
        // cliente identificado: sin tope, dejamos pasar.
        if (!esConsumidorFinal) {
            return res;
        }
        // Total del pedido CON impuestos (mismo campo que usa el core en esta
        // misma clase para comparar montos pagados).
        const total = this.order.priceIncl;
        // Si no supera el tope, la boleta al Consumidor Final es válida.
        if (total <= TOPE_BOLETA_CF) {
            return res;
        }
        // ---- Supera S/ 700 con Consumidor Final: se bloquea la emisión ----
        // Formateador de moneda del POS para mostrar montos legibles.
        const fmt = this.pos.env.utils.formatCurrency;
        // Aviso bloqueante; al pulsar "Cambiar cliente" abrimos la selección
        // de cliente para que el cajero elija uno identificado (DNI/RUC).
        this.pos.dialog.add(AlertDialog, {
            title: _t("Boleta no permitida para Consumidor Final"),
            body: _t(
                "Una boleta al Consumidor Final no puede superar %(tope)s.\n" +
                    "El total del pedido es %(total)s.\n\n" +
                    "Debe cambiar el cliente por uno identificado (con DNI o RUC) " +
                    "para poder emitir el comprobante.",
                { tope: fmt(TOPE_BOLETA_CF), total: fmt(total) }
            ),
            confirmLabel: _t("Cambiar cliente"),
            // Al confirmar, abrimos directamente la lista para elegir cliente.
            confirm: () => this.pos.selectPartner(),
        });
        // Devolver false impide que el pedido se valide/cobre.
        return false;
    },
});
