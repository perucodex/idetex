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

            const report = reportModel.getAll().filter(q => q.quantity > 0);  // solo mostrar lotes con stock disponible; los que lleguen a 0 via sync incremental quedan ocultos automáticamente
            const searchWord = (this.pos.searchProductWord || "").trim().toLowerCase();

            if (!searchWord) {
                return report.slice(0, 30);
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
            }).slice(0, 30);
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
     * Helper: indica si el rollo está bloqueado por OTRO pedido POS guardado.
     * Devuelve true si is_reserved=true y reserved_by_order_id NO es la orden actual.
     * Si es la orden actual, se considera "ya está en el pedido" (lo maneja isQuantInOrder).
     */
    isQuantReservedByOtherOrder(quant) {
        if (!quant || !quant.is_reserved) return false;                         // no bloqueado → libre
        const currentOrder = this.pos.getOrder();
        // reserved_by_order_id puede llegar como record, integer o array [id, "nombre"]
        const rawOrderId = quant.reserved_by_order_id;
        const reservedOrderId = rawOrderId?.id ?? (Array.isArray(rawOrderId) ? rawOrderId[0] : rawOrderId);
        // Si la reserva pertenece a la orden actual del cajero, no la consideramos "ajena"
        return currentOrder ? reservedOrderId !== currentOrder.id : true;
    },

    /*
     * Gestiona la selección manual de filas.
     * Bloquea la selección si el rollo está reservado por otro pedido POS guardado.
     */
    toggleQuantSelection(quant) {
        // Bloqueo por reserva: notificar y abortar
        if (this.isQuantReservedByOtherOrder(quant)) {
            if (this.notification) {
                this.notification.add(
                    `El rollo ${quant.lot_name || ''} está bloqueado por otro pedido guardado.`,
                    { type: "warning", sticky: false }
                );
            }
            return;                                                             // no permitir selección
        }

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
     * Intercepta escaneos de código de barras tipo lot.
     * Blindaje (2026-07-08): el escaneo solo se acepta si el lote corresponde a un
     * rollo REAL de Existencias PdV, con stock, no reservado y no repetido en el
     * pedido. Cualquier otro caso se rechaza con sonido + aviso, en vez de dejar
     * que el lector genérico agregue una línea a medias (producto+peso sin rollo).
     */
    async _barcodeGS1Action(parsed_results) {
        const lotBarcode = parsed_results.find((element) => element.type === "lot");
        if (lotBarcode && lotBarcode.value) {
            const reportModel = this.pos.models["idtx.pos.stock.report"];
            if (reportModel) {
                // Normalización: sin espacios y sin distinguir mayúsculas/minúsculas,
                // para tolerar escáneres que envían "c383604-088" en vez de "C383604-088"
                const scanned = String(lotBarcode.value).trim().toLowerCase();
                const quant = reportModel.getAll().find(
                    q => (q.lot_name || "").trim().toLowerCase() === scanned
                );
                // Rechazo 1: el lote no corresponde a NINGÚN rollo conocido
                if (!quant) {
                    if (this.sound) this.sound.play("scan-error");                   // sonido de error
                    if (this.notification) {
                        this.notification.add(
                            `Rollo "${lotBarcode.value}" NO encontrado en Existencias PdV. ` +
                            `Escaneo rechazado: verifique el escáner o refresque el POS (F5) si el rollo es de una carga reciente.`,
                            { type: "danger", sticky: true }
                        );
                    }
                    return;                                                     // no procesar el escaneo
                }
                // Rechazo 2: rollo sin stock disponible (ya vendido o en cero)
                if (!(quant.quantity > 0)) {
                    if (this.sound) this.sound.play("scan-error");
                    if (this.notification) {
                        this.notification.add(
                            `Rollo ${quant.lot_name} sin stock disponible. Escaneo rechazado.`,
                            { type: "danger", sticky: true }
                        );
                    }
                    return;
                }
                // Rechazo 3: rollo bloqueado por otro pedido guardado
                if (this.isQuantReservedByOtherOrder(quant)) {
                    if (this.sound) this.sound.play("scan-error");
                    if (this.notification) {
                        this.notification.add(
                            `Rollo ${quant.lot_name} bloqueado por otro pedido guardado. No se puede escanear.`,
                            { type: "warning", sticky: false }
                        );
                    }
                    return;
                }
                // Rechazo 4: el rollo ya está en el pedido actual (escaneo repetido)
                if (this.isQuantInOrder(quant)) {
                    if (this.sound) this.sound.play("scan-error");
                    if (this.notification) {
                        this.notification.add(
                            `Rollo ${quant.lot_name} ya está en el pedido. Escaneo repetido ignorado.`,
                            { type: "warning", sticky: false }
                        );
                    }
                    return;
                }
                // Canonizar el lote con el nombre EXACTO del sistema (mayúsculas correctas):
                // así la línea guarda el lote real y la reserva por nombre funciona al guardar.
                lotBarcode.value = quant.lot_name;
            }
        }
        // Caso normal: delegar al comportamiento original
        return super._barcodeGS1Action(parsed_results);
    },

    /*
     * AGREGA PRODUCTOS EN BLOQUE: Técnica silenciosa para lotes.
     * Filtra rollos que pudieran haber sido reservados por otro pedido entre selección y agregado.
     */
    async addSelectedQuants() {
        const selectedIds = Object.keys(this.idtxState.selectedQuants).map(id => parseInt(id));
        if (selectedIds.length === 0) return;

        const reportModel = this.pos.models["idtx.pos.stock.report"];
        // Filtrar rollos válidos: existen y no están reservados por otra orden
        const allQuants = selectedIds.map(id => reportModel.get(id)).filter(q => q);
        const blockedQuants = allQuants.filter(q => this.isQuantReservedByOtherOrder(q));
        const quantsToAdd = allQuants.filter(q => !this.isQuantReservedByOtherOrder(q));

        // Avisar al usuario si alguno fue rechazado por bloqueo (race condition con otra caja)
        if (blockedQuants.length > 0 && this.notification) {
            this.notification.add(
                `${blockedQuants.length} rollo(s) fueron bloqueados por otro pedido y se omitieron.`,
                { type: "warning", sticky: false }
            );
        }

        console.log('[IDTX] addSelectedQuants selectedIds:', selectedIds, 'quantsToAdd:', quantsToAdd.length);

        for (const quant of quantsToAdd) {
            // quant.product_id puede ser: el record del producto (Many2one conectado),
            // un entero (ID raw si no se conectó), o un array [id,"nombre"] (de search_read).
            const rawPid = quant.product_id;
            const pId = rawPid?.id ?? (Array.isArray(rawPid) ? rawPid[0] : rawPid);
            const product = this.pos.models["product.product"].get(pId);

            console.log('[IDTX] quant:', quant.lot_name, 'rawPid:', rawPid, 'pId:', pId, 'product:', product?.id, 'tmpl:', product?.product_tmpl_id?.id, 'qty:', quant.quantity);

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
