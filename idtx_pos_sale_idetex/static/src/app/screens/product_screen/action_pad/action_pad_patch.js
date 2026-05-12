/** @odoo-module **/

import { ActionpadWidget } from "@point_of_sale/app/screens/product_screen/action_pad/action_pad";
import { patch } from "@web/core/utils/patch";

patch(ActionpadWidget.prototype, {
    /**
     * Calcula el total de kilos (suma de cantidades de todas las líneas)
     */
    get totalKilos() {
        const order = this.pos.getOrder();
        if (!order) return 0;
        return order.getOrderlines().reduce((acc, line) => acc + line.getQuantity(), 0);
    },
    /**
     * Calcula el total de rollos (número de líneas en el pedido)
     */
    get totalRolls() {
        const order = this.pos.getOrder();
        if (!order) return 0;
        return order.getOrderlines().length;
    }
});
