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
        // Deshabilitar "Cant.": la cantidad de un rollo NUNCA se edita en el carrito.
        // Un corte de rollo se hace en Existencias PdV → Partir rollo (crea el lote
        // hijo -C## y mueve los kg en stock). Si el cajero cambiara los kilos aquí,
        // vendería una cantidad que no coincide con el rollo físico ni con el kardex.
        const qtyBtn = buttons.find(b => b.value === "quantity");
        if (qtyBtn) {
            qtyBtn.disabled = true;                              // visible pero gris e inerte
        }
        return buttons;
    }
});
