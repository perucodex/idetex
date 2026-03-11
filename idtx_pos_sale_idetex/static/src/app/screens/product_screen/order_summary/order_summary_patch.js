/** @odoo-module */

import { OrderSummary } from "@point_of_sale/app/screens/product_screen/order_summary/order_summary";
import { GroupOrderline } from "../../../components/group_orderline/group_orderline";
import { patch } from "@web/core/utils/patch";

patch(OrderSummary, {
    components: {
        ...OrderSummary.components,
        GroupOrderline,
    }
});

patch(OrderSummary.prototype, {
    /*
     * Maneja el click en la cabecera del grupo.
     */
    clickGroup(ev, group) {
        if (group.children && group.children.length > 0) {
            this.clickLine(ev, group.children[0]);
        }
    },

    /*
     * Override crítico: Propagación de precios en grupo.
     * Si cambiamos el precio de una línea que tiene Color, asumimos que es un cambio para todo el lote/color.
     */
    async setLinePrice(line, price) {
        // Ejecutamos la lógica original para la línea seleccionada (y manejo de UI)
        await super.setLinePrice(line, price);

        // Lógica de propagación masiva
        if (line.color_name) {
            const order = this.pos.getOrder();
            const siblings = order.lines.filter(l =>
                l.uuid !== line.uuid && // No repetimos la actual
                l.product_id.id === line.product_id.id &&
                l.color_name === line.color_name
            );

            // Aplicamos el precio a los hermanos sin trigger de UI extra
            for (const sibling of siblings) {
                sibling.price_type = "manual";
                sibling.setUnitPrice(price);
            }
        }
    }
});
