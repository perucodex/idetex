/** @odoo-module **/

import { ProductScreen } from "@point_of_sale/app/screens/product_screen/product_screen";
import { patch } from "@web/core/utils/patch";
import { onMounted } from "@odoo/owl";

patch(ProductScreen.prototype, {
    setup() {
        super.setup(...arguments);
        onMounted(() => {
            this.pos.numpadMode = "price";
        });
    },

    /*
     * Override getNumpadButtons: cambiar el texto del botón "% de descuento" / "% Disc" por solo "%".
     * El traductor de Odoo expande "%" a "% de descuento" en español, así que aquí lo forzamos
     * después de que el método base construye la lista.
     */
    getNumpadButtons() {
        const buttons = super.getNumpadButtons(...arguments);   // obtener la lista original
        const discBtn = buttons.find(b => b.value === "discount");
        if (discBtn) {
            discBtn.text = "%";                                  // forzar el símbolo corto
        }
        return buttons;
    }
});
