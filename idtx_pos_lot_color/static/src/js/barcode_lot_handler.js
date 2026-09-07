import { ProductScreen } from "@point_of_sale/app/screens/product_screen/product_screen";
import { patch } from "@web/core/utils/patch";

patch(ProductScreen.prototype, {
    async _barcodeProductAction(code) {
        const barcodeString = typeof code === 'string' ? code : (code.base_code || code.code);
        // Optimización (2026-07-10): las etiquetas GS1 de rollos miden ~38 caracteres;
        // ningún código de barras de producto es así. Saltamos las 4 búsquedas nativas
        // (por código completo) que siempre fallaban para estas etiquetas.
        const esEtiquetaGS1 = barcodeString && barcodeString.startsWith('01') && barcodeString.length > 20;
        let product = esEtiquetaGS1 ? null : await this._getProductByBarcode(code);
        let barcodeOption = code;
        let productQty = 1; // Default quantity
        // Color del rollo escaneado: se asigna a la línea al final, igual que
        // lo hace el widget de Existencias (antes las líneas escaneadas quedaban sin color)
        let rollColorName = null;

        // 0. Búsqueda por GS1 (QR Especial)
        if (!product && barcodeString && barcodeString.startsWith('01')) {
            console.log("[IDTX] Detectado posible código GS1:", barcodeString);
            const gs1Data = this._parseGS1(barcodeString);
            if (gs1Data) {
                console.log("[IDTX] GS1 Parsed:", gs1Data);
                // Buscar por GTIN vía mapa cacheado (antes: recorrido lineal de
                // todos los productos en cada escaneo)
                product = this._idtxProductByGtin(gs1Data.gtin);
                
                if (!product) {
                    console.log("[IDTX] GTIN no encontrado en memoria. Buscando en servidor:", gs1Data.gtin);
                    const records = await this.pos.loadNewProducts([["barcode", "=", gs1Data.gtin]]);
                    if (records && records["product.product"]?.length > 0) {
                        this.pos.data.models.loadConnectedData(records);
                        product = this.pos.models["product.product"].get(records["product.product"][0].id);
                    }
                }

                if (product) {
                    // ===== Blindaje (2026-07-08): validar el lote contra Existencias PdV =====
                    // Antes se aceptaba el lote TAL CUAL venía del escáner: un escáner
                    // desconfigurado (o un teclado a través de una VM) metía lotes
                    // corruptos ("c#83604-080") y se guardaban pedidos con rollos
                    // inexistentes, sin reserva y sin trazabilidad. Ahora el lote debe
                    // corresponder a un rollo REAL, con stock y libre; si no, se rechaza
                    // con aviso en pantalla para que el cajero se entere al instante.
                    const reportModel = this.pos.models["idtx.pos.stock.report"];
                    if (reportModel) {
                        // Comparación sin distinguir mayúsculas/minúsculas ni espacios
                        const scanned = String(gs1Data.lot || "").trim().toLowerCase();
                        const quant = reportModel.getAll().find(
                            q => (q.lot_name || "").trim().toLowerCase() === scanned
                        );
                        const notificar = (msg, tipo, fijo) => {
                            if (this.sound) this.sound.play("scan-error");
                            if (this.env.services.notification) {
                                this.env.services.notification.add(msg, { type: tipo, sticky: fijo });
                            }
                            this.numberBuffer.reset();
                        };
                        // Rechazo 1: el lote no corresponde a NINGÚN rollo conocido
                        if (!quant) {
                            notificar(
                                `Rollo "${gs1Data.lot}" NO encontrado en Existencias PdV. Escaneo rechazado: ` +
                                `verifique el escáner o refresque el POS (F5) si el rollo es de una carga reciente.`,
                                "danger", true
                            );
                            return;
                        }
                        // Rechazo 2: rollo sin stock disponible (ya vendido o en cero)
                        if (!(quant.quantity > 0)) {
                            notificar(`Rollo ${quant.lot_name} sin stock disponible. Escaneo rechazado.`, "danger", true);
                            return;
                        }
                        // Rechazo 3: rollo bloqueado por otro pedido guardado
                        // (isQuantReservedByOtherOrder viene del patch de idtx_pos_sale_idetex)
                        if (this.isQuantReservedByOtherOrder && this.isQuantReservedByOtherOrder(quant)) {
                            notificar(`Rollo ${quant.lot_name} bloqueado por otro pedido guardado. No se puede escanear.`, "warning", false);
                            return;
                        }
                        // Lote canónico (mayúsculas correctas) y peso del SISTEMA (no el de
                        // la etiqueta): si el rollo se partió, el stock real es el vigente.
                        gs1Data.lot = quant.lot_name;
                        productQty = quant.quantity;
                        rollColorName = quant.color_name || "";
                    } else {
                        productQty = gs1Data.weight;
                    }
                    barcodeOption = { type: 'lot', code: gs1Data.lot };
                }
            }
        }

        if (!product) {
            const searchTerm = typeof code === 'string' ? code : code.code;
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
                    const reportRecords = await this.pos.data.searchRead("idtx.pos.stock.report", domain, ["product_id", "lot_name", "roll_name", "quantity", "color_name"], { limit: 1 });

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
                            rollColorName = reportRaw.color_name || "";
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
            // VERIFICAR SI EL ROLLO/LOTE YA ESTÁ EN EL PEDIDO
            const order = this.pos.getOrder();
            const lotName = barcodeOption?.code || barcodeOption;
            if (order && lotName && typeof lotName === 'string') {
                const alreadyInOrder = order.lines.some(line => 
                    line.pack_lot_ids.some(lot => lot.lot_name === lotName)
                );
                if (alreadyInOrder) {
                    if (this.env.services.notification) {
                        this.env.services.notification.add(
                            `El rollo/lote ${lotName} ya está en el pedido.`,
                            { type: "warning", sticky: false }
                        );
                    }
                    this.numberBuffer.reset();
                    return;
                }
            }

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
            // Asignar el color del rollo a la línea recién creada,
            // igual que lo hace el widget de Existencias (addSelectedQuants)
            if (rollColorName !== null && order) {
                const newLine = order.getSelectedOrderline();
                if (newLine) {
                    newLine.color_name = rollColorName;
                }
            }
            this.numberBuffer.reset();
            this.showOptionalProductPopupIfNeeded(product);
            return;
        }

        // Fallback al comportamiento original
        return super._barcodeProductAction(...arguments);
    },

    /**
     * Mapa GTIN → producto, construido una sola vez y reconstruido solo si
     * cambia la cantidad de productos cargados (ej. loadNewProducts).
     * Evita recorrer todos los productos en cada escaneo.
     */
    _idtxProductByGtin(gtin) {
        const productos = this.pos.models["product.product"].getAll();
        if (!this._idtxGtinMap || this._idtxGtinMapSize !== productos.length) {
            this._idtxGtinMap = new Map();
            for (const p of productos) {
                if (p.barcode) {
                    this._idtxGtinMap.set(p.barcode, p);
                }
            }
            this._idtxGtinMapSize = productos.length;
        }
        return this._idtxGtinMap.get(gtin);
    },

    /**
     * Parsea un string en formato GS1 (01 GTIN 3102 WEIGHT 10 LOT)
     * @param {string} code
     * @returns {object|null}
     */
    _parseGS1(code) {
        try {
            // Ejemplo: 0177512340041039310200247210C370225-692
            // 01 -> GTIN (14 dígitos)
            // 3102 -> Peso (6 dígitos, 2 decimales)
            // 10 -> Lote (Variable hasta el final)
            
            const gtin = code.substring(2, 16);
            let weight = 1;
            let lot = "";

            // El peso (3102) usualmente sigue al GTIN (índice 16)
            const weightIndex = code.indexOf('3102', 16);
            let nextIndex = 16;

            if (weightIndex !== -1) {
                weight = parseFloat(code.substring(weightIndex + 4, weightIndex + 10)) / 100;
                nextIndex = weightIndex + 10;
            }

            // El lote (10) sigue después del peso o directamente después del GTIN
            const lotIndex = code.indexOf('10', nextIndex);

            if (lotIndex !== -1) {
                lot = code.substring(lotIndex + 2);
            }

            return {
                gtin: gtin,
                weight: weight,
                lot: lot
            };
        } catch (e) {
            console.error("[IDTX] Error parsing GS1 barcode:", e);
            return null;
        }
    }
});
