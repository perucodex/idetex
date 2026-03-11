import { ProductScreen } from "@point_of_sale/app/screens/product_screen/product_screen";
import { patch } from "@web/core/utils/patch";

patch(ProductScreen.prototype, {
    async _barcodeProductAction(code) {
        let product = await this._getProductByBarcode(code);
        let barcodeOption = code;
        let productQty = 1; // Default quantity

        if (!product) {
            const searchTerm = code.code;
            console.log("[IDTX] Producto no encontrado por código de barras. Buscando por referencia/lote:", searchTerm);

            // 1. Búsqueda por default_code (Referencia Interna)
            product = this.pos.models["product.product"].getAll().find(p =>
                p.default_code && p.default_code.toLowerCase() === searchTerm.toLowerCase()
            );

            if (!product) {
                console.log("[IDTX] Buscando producto por referencia en servidor:", searchTerm);
                const records = await this.pos.loadNewProducts([["default_code", "=", searchTerm]]);
                if (records && records["product.product"]?.length > 0) {
                    this.pos.data.models.loadConnectedData(records);
                    const prodId = records["product.product"][0].id;
                    product = this.pos.models["product.product"].get(prodId);
                }
            }

            // 2. Búsqueda en Reporte Técnico (Lote o Referencia) para obtener el peso real
            if (!product) {
                console.log("[IDTX] Buscando en Reporte Técnico por Lote/Referencia:", searchTerm);
                try {
                    const domain = ["|", ["lot_name", "ilike", searchTerm], ["roll_name", "ilike", searchTerm]];
                    const reportRecords = await this.pos.data.searchRead("idtx.pos.stock.report", domain, ["product_id", "lot_name", "roll_name", "quantity"], { limit: 1 });

                    if (reportRecords && reportRecords.length > 0) {
                        const reportRaw = reportRecords[0];
                        console.log("[IDTX] Registro encontrado en reporte técnico:", reportRaw);

                        const prodId = Array.isArray(reportRaw.product_id) ? reportRaw.product_id[0] : reportRaw.product_id;
                        product = this.pos.models["product.product"].get(prodId);

                        if (!product) {
                            console.log("[IDTX] Cargando producto desde servidor ID:", prodId);
                            const records = await this.pos.loadNewProducts([["id", "=", prodId]]);
                            if (records && records["product.product"]?.length > 0) {
                                this.pos.data.models.loadConnectedData(records);
                                product = this.pos.models["product.product"].get(prodId);
                            }
                        }

                        if (product) {
                            barcodeOption = { type: 'lot', code: reportRaw.lot_name };
                            productQty = reportRaw.quantity || 1;
                            console.log("[IDTX] Peso detectado:", productQty, "Lote:", reportRaw.lot_name);
                        }
                    } else {
                        // 3. Fallback: Búsqueda directa en Lotes (stock.lot) si no está en el reporte
                        console.log("[IDTX] No encontrado en reporte. Buscando en stock.lot:", searchTerm);
                        const serverLots = await this.pos.data.searchRead("stock.lot", [["name", "ilike", searchTerm]], ["product_id", "name"], { limit: 1 });
                        if (serverLots && serverLots.length > 0) {
                            const lotRaw = serverLots[0];
                            const prodId = Array.isArray(lotRaw.product_id) ? lotRaw.product_id[0] : lotRaw.product_id;

                            product = this.pos.models["product.product"].get(prodId);
                            if (!product) {
                                const records = await this.pos.loadNewProducts([["id", "=", prodId]]);
                                if (records && records["product.product"]?.length > 0) {
                                    this.pos.data.models.loadConnectedData(records);
                                    product = this.pos.models["product.product"].get(prodId);
                                }
                            }
                            if (product) {
                                barcodeOption = { type: 'lot', code: lotRaw.name };
                                productQty = 1; // No hay peso en stock.lot básico
                            }
                        }
                    }
                } catch (err) {
                    console.error("[IDTX] Error en búsqueda avanzada de barcode:", err);
                }
            }
        }

        if (product) {
            console.log("[IDTX] Agregando al pedido:", product.display_name, "Cant:", productQty, "Opciones:", barcodeOption);
            await this.pos.addLineToCurrentOrder(
                {
                    product_id: product,
                    product_tmpl_id: product.product_tmpl_id,
                    qty: productQty
                },
                { code: barcodeOption, merge: false }, // merge: false para evitar agrupar rollos distintos
                product.needToConfigure()
            );
            this.numberBuffer.reset();
            this.showOptionalProductPopupIfNeeded(product);
            return;
        }

        // Fallback al comportamiento original
        return super._barcodeProductAction(...arguments);
    }
});
