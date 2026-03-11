/** @odoo-module */

import { Component, useState } from "@odoo/owl";
import { Orderline } from "@point_of_sale/app/components/orderline/orderline";
import { useService } from "@web/core/utils/hooks";

export class GroupOrderline extends Component {
    static template = "idtx_pos_sale_idetex.GroupOrderline";
    static components = { Orderline };
    static props = {
        group: Object,
        onClick: { type: Function, optional: true },
        onLineClick: { type: Function, optional: true },
    };

    setup() {
        this.state = useState({
            expanded: false,
        });
        this.numberBuffer = useService("number_buffer");
    }

    get group() {
        return this.props.group;
    }

    toggleExplode(ev) {
        ev.stopPropagation();
        this.state.expanded = !this.state.expanded;
    }

    /*
     * Maneja el click en la cabecera del grupo.
     * Si estamos en modo PRECIO, aplicamos el cambio al grupo?
     * O seleccionamos el grupo para que el Numpad actúe sobre él?
     * Por ahora, seleccionamos el primer hijo para contexto, pero marcamos visualmente el grupo.
     */
    async onClick(ev) {
        // Lógica de selección de grupo
        if (this.props.onClick) {
            this.props.onClick(ev, this.group);
        }
    }

    /*
     * Helpers de visualización
     */
    get displayPrice() {
        try {
            const price = this.group.displayPrice;
            if (this.env.utils && typeof this.env.utils.formatCurrency === 'function') {
                return this.env.utils.formatCurrency(price);
            }
            return price.toFixed(2); // Fallback
        } catch (e) {
            console.error("Error formatting price:", e);
            return "0.00";
        }
    }

    get totalQuantity() {
        try {
            return this.group.getQuantityStr(); // Devuelve string con unidades
        } catch (e) {
            console.error("Error getting quantity:", e);
            return "0 Kg";
        }
    }

    /*
     * Eliminar un ítem individual del grupo
     */
    async onDeleteItem(line) {
        // Necesitamos acceso al pedido actual para eliminar
        // Asumiendo que line es una instancia de PosOrderline
        const order = line.order_id;
        if (order) {
            order.removeOrderline(line);
        }
    }
}
