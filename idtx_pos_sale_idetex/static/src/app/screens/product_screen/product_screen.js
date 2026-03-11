/*
 * Parche optimizado para Odoo 19 - Idetex.
 * Gestiona el estado de selección múltiple de forma independiente (idtxState).
 */
import { ProductScreen } from "@point_of_sale/app/screens/product_screen/product_screen";
import { patch } from "@web/core/utils/patch";
import { useState } from "@odoo/owl";

patch(ProductScreen.prototype, {
    /*
     * Inicialización del componente.
     * Creamos un estado idtxState separado para evitar conflictos con el estado nativo.
     */
    setup() {
        super.setup(...arguments);
        this.idtxState = useState({
            selectedQuants: {},
            selectedCount: 0,
        });
        this.notification = this.env.services.notification; // Access via env directly or useService if imported
    },

    /*
     * FILTRADO DE STOCK: Busca por cada palabra en todas las columnas técnicas.
     */
    get quantsToDisplay() {
        try {
            // Safety check for models
            if (!this.pos || !this.pos.models) {
                return [];
            }

            const reportModel = this.pos.models["idtx.pos.stock.report"];
            if (!reportModel) {
                return [];
            }

            const report = reportModel.getAll();
            const searchWord = (this.pos.searchProductWord || "").trim().toLowerCase();

            if (!searchWord) {
                return report.slice(0, 100);
            }

            const words = searchWord.split(/\s+/).filter(w => w.length > 0);

            return report.filter(q => {
                const searchableText = [
                    q.product_name,
                    q.product_code,
                    q.lot_name,
                    q.color_name,
                    q.color_code,
                    q.partida,
                    q.roll_name,
                    q.product_label,
                    q.partida_label
                ].map(v => v ? String(v).toLowerCase() : "").join(" ");

                return words.every(word => searchableText.includes(word));
            }).slice(0, 100);
        } catch (error) {
            console.error("Error in quantsToDisplay:", error);
            return [];
        }
    },

    /*
     * Verifica si un ítem ya está en el pedido actual.
     */
    isQuantInOrder(quant) {
        if (!quant || !quant.lot_name) return false;
        const order = this.pos.getOrder();
        if (!order) return false;

        return order.lines.some(line =>
            line.pack_lot_ids.some(lot => lot.lot_name === quant.lot_name)
        );
    },

    /*
     * Gestiona la selección manual de filas.
     */
    toggleQuantSelection(quant) {
        if (this.isQuantInOrder(quant)) return;

        if (this.idtxState.selectedQuants[quant.id]) {
            delete this.idtxState.selectedQuants[quant.id];
            this.idtxState.selectedCount--;
        } else {
            this.idtxState.selectedQuants[quant.id] = true;
            this.idtxState.selectedCount++;
        }
    },

    /*
     * AGREGA PRODUCTOS EN BLOQUE: Técnica silenciosa para lotes.
     */
    async addSelectedQuants() {
        const selectedIds = Object.keys(this.idtxState.selectedQuants).map(id => parseInt(id));
        if (selectedIds.length === 0) return;

        const reportModel = this.pos.models["idtx.pos.stock.report"];
        const quantsToAdd = selectedIds.map(id => reportModel.get(id)).filter(q => q);

        for (const quant of quantsToAdd) {
            const pId = Array.isArray(quant.product_id) ? quant.product_id[0] : (quant.product_id?.id || quant.product_id);
            const product = this.pos.models["product.product"].get(pId);

            if (product && !this.isQuantInOrder(quant)) {
                // Truco de bypass: simulamos que el lote viene de un escáner.
                const options = {
                    merge: false, // Una línea por cada rollo/lote para mayor claridad.
                    code: { type: 'lot', code: quant.lot_name || "" }
                };

                // Enviamos los kilos reales (quant.quantity) en el objeto de valores.
                await this.pos.addLineToCurrentOrder({
                    product_id: product,
                    product_tmpl_id: product.product_tmpl_id,
                    qty: quant.quantity,
                }, options, false);

                // Asignamos el nombre del color a la línea recién creada
                const order = this.pos.getOrder();
                if (order) {
                    const line = order.getSelectedOrderline();
                    if (line) {
                        line.color_name = quant.color_name || "";
                    }
                }
            }
        }


        // Feedback visual para el usuario
        if (this.notification) {
            this.notification.add(
                `${quantsToAdd.length} ítems agregados al pedido correctamente.`,
                {
                    type: "success",
                    sticky: false,
                }
            );
        }

        this.idtxState.selectedQuants = {};
        this.idtxState.selectedCount = 0;
    },

    /*
     * Helper para formatear cantidad de stock.
     * Evita errores si this.env.utils no tiene formatProductQty.
     */
    getFormattedStock(qty) {
        if (this.env.utils && typeof this.env.utils.formatProductQty === 'function') {
            return this.env.utils.formatProductQty(qty);
        }
        // Fallback seguro usando localización o toFixed
        return (typeof qty === 'number' ? qty.toFixed(2) : qty) + " Kg";
    }
});
