/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { SaleOrderLineListRenderer } from "@sale/js/sale_order_line_field/sale_order_line_field";

// Pinta en gris (como una sección) las líneas marcadas como complemento.
// El campo `is_complement` solo existe en sale.order.line, por lo que en
// cualquier otra lista record.data.is_complement es undefined (sin efecto).
patch(SaleOrderLineListRenderer.prototype, {
    getRowClass(record) {
        const classNames = super.getRowClass(record);
        if (record.data.is_complement) {
            return `${classNames} o_is_complement_line`;
        }
        return classNames;
    },
});
