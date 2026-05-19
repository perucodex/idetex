/** @odoo-module **/

import { ActionpadWidget } from "@point_of_sale/app/screens/product_screen/action_pad/action_pad";
import { patch } from "@web/core/utils/patch";

// Permitir que el widget reciba una orden explícita via prop "order".
// Si no se pasa, sigue usando la orden actual del POS (this.pos.getOrder()).
// Esto permite reutilizar el ActionpadWidget en TicketScreen mostrando los totales
// de la orden seleccionada para reembolso, no de la orden activa vacía.
ActionpadWidget.props = {
    ...ActionpadWidget.props,
    order: { type: [Object, { value: null }], optional: true },
};

patch(ActionpadWidget.prototype, {
    /**
     * Orden a mostrar en el resumen: prop "order" si se pasó (caso TicketScreen / reembolso),
     * sino la orden actual del POS (caso ProductScreen / venta normal).
     */
    get currentOrder() {
        return this.props.order || this.pos.getOrder();
    },
    /**
     * Total de kilos = suma de quantities de todas las líneas de la orden de referencia.
     */
    get totalKilos() {
        const order = this.currentOrder;
        if (!order) return 0;
        return order.getOrderlines().reduce((acc, line) => acc + line.getQuantity(), 0);
    },
    /**
     * Total de rollos = número de líneas de la orden de referencia.
     */
    get totalRolls() {
        const order = this.currentOrder;
        if (!order) return 0;
        return order.getOrderlines().length;
    }
});
