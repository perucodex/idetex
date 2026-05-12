/** @odoo-module */

import { Orderline } from "@point_of_sale/app/components/orderline/orderline";
import { patch } from "@web/core/utils/patch";

patch(Orderline.prototype, {
    /*
     * Forzamos la visualización del precio unitario siempre que estemos en modo pantalla ('display'),
     * independientemente de si el precio ha cambiado o no.
     */
    get lineScreenValues() {
        const values = super.lineScreenValues;
        const line = this.props.line;

        // Si no hay línea o datos base, retornamos lo original
        if (!line || !values) return values;

        // Forzamos displayPriceUnit en modo pantalla
        if (this.props.mode === 'display') {
            const priceUnit = `${line.currencyDisplayPriceUnit} / ${line.product_id?.uom_id?.name || ""
                }`;

            // Sobrescribimos displayPriceUnit para que siempre tenga valor si hay precio
            if (line.price !== 0) {
                values.displayPriceUnit = priceUnit;
            }
        }

        // Agregamos color y lote a los valores de pantalla
        values.color_name = line.color_name || "";
        // Extraemos el primer lote de la lista de lotes y limpiamos el texto "Lot Number"
        let firstLot = values.lotLines && values.lotLines.length > 0 ? values.lotLines[0] : "";
        if (typeof firstLot === 'string') {
            firstLot = firstLot.replace(/Lot Number/gi, '').replace(':', '').trim();
        }
        values.lot_name = firstLot;

        return values;
    }
});
