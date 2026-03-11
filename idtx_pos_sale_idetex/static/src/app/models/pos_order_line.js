/** @odoo-module */

import { PosOrderline } from "@point_of_sale/app/models/pos_order_line";
import { patch } from "@web/core/utils/patch";

patch(PosOrderline.prototype, {
    /*
     * Modificamos setUnitPrice para que el precio digitado se considere "Precio Final" (IVA Incluido).
     */
    setUnitPrice(price) {
        let parsedPrice = !isNaN(price) ?
            price :
            (isNaN(parseFloat(price)) ? 0 : parseFloat("" + price));

        const taxes = this.tax_ids || (this.product_id ? this.product_id.taxes_id : []);

        if (taxes && taxes.length > 0 && parsedPrice !== 0) {
            const ProductPrice = this.models["decimal.precision"].find(
                (dp) => dp.name === "Product Price"
            );

            let taxFactor = 1.0;
            for (const tax of taxes) {
                if (tax.amount_type === 'percent' && !tax.price_include) {
                    taxFactor += (tax.amount / 100);
                }
            }

            if (taxFactor > 1.0) {
                parsedPrice = parsedPrice / taxFactor;
                if (ProductPrice) {
                    parsedPrice = ProductPrice.round(parsedPrice);
                }
            }
        }

        super.setUnitPrice(parsedPrice);
    },

    /*
     * Validamos que la cantidad ingresada no supere el stock real del lote.
     * VERSIÓN ROBUSTA: Búsqueda flexible y manejo de tipos.
     */
    setQuantity(quantity, keep_price) {
        const newQty = typeof quantity === 'string' ? parseFloat(quantity) : quantity;

        // Validamos solo ventas (qty > 0) con lotes asignados
        if (newQty && newQty > 0 && this.pack_lot_ids && this.pack_lot_ids.length > 0) {
            // Buscamos el primer lote válido (asumiendo 1 lote por línea como es usual en este flujo)
            const packLot = this.pack_lot_ids.find(l => l.lot_name);

            if (packLot) {
                const lotName = packLot.lot_name.trim();
                const reportModel = this.models["idtx.pos.stock.report"];
                const currentProductId = this.product_id.id;

                // Búsqueda en el reporte
                const quants = reportModel.getAll();
                const quant = quants.find(q => {
                    const qLot = q.lot_name ? q.lot_name.trim() : "";
                    const qProdId = Array.isArray(q.product_id) ? q.product_id[0] : (q.product_id?.id || q.product_id);
                    return qLot === lotName && qProdId == currentProductId;
                });

                if (quant) {
                    // SE ENCONTRÓ EL LOTE: Validamos stock
                    // Tolerancia 0.01 para errores de redondeo flotante
                    if (newQty > (quant.quantity + 0.01)) {
                        // EXCESO DE STOCK: Forzamos al máximo y notificamos
                        arguments[0] = quant.quantity;

                        if (this.env && this.env.services && this.env.services.notification) {
                            this.env.services.notification.add(
                                `Stock insuficiente. Máximo permitido: ${quant.quantity} Kg`,
                                { type: 'warning', sticky: false }
                            );
                        }
                    }
                }
            }
        }

        return super.setQuantity(...arguments);
    },

    init_from_JSON(json) {
        super.init_from_JSON(...arguments);
        this.color_name = json.color_name;
    },

    export_as_JSON() {
        const json = super.export_as_JSON(...arguments);
        json.color_name = this.color_name || "";
        return json;
    }
});
