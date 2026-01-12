/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { PosOrderline } from "@point_of_sale/app/models/pos_order_line";
import { PosStore } from "@point_of_sale/app/services/pos_store";

// Mantén una referencia estable a los lots cargados en POS
let STOCK_LOTS = null;

// Tomamos lo que ya carga tu módulo idtx_pos_lot_color: this["stock.lot"]
patch(PosStore.prototype, {
    async processServerData() {
        await super.processServerData(...arguments);
        // tu módulo idtx_pos_lot_color ya hace: this["stock.lot"] = await this.data.searchRead(...)
        // aquí solo “capturamos” esa lista para usarla siempre
        STOCK_LOTS = this["stock.lot"] || STOCK_LOTS;
        // debug opcional:
    },
});

function getProductCode(product) {
    return (
        product?.default_code ||
        product?.barcode ||
        (product?.id != null ? String(product.id) : null)
    );
}

function toArray(value) {
    if (!value) return [];
    if (Array.isArray(value)) return value;
    if (Array.isArray(value.models)) return value.models;
    if (typeof value.values === "function") return Array.from(value.values()); // Map-like
    if (value[Symbol.iterator]) return Array.from(value); // iterable
    if (typeof value === "object") return Object.values(value);
    return [];
}

function getLotName(packLot) {
    return packLot?.lot_name || packLot?.lotName || packLot?.name || null;
}

function getOrderFromLine(line) {
    return line?.order || line?.order_id || null;
}

function getOrderLines(order) {
    if (!order) return [];
    if (order.lines) return toArray(order.lines); // tu build
    if (order.orderlines) return toArray(order.orderlines);
    if (typeof order.get_orderlines === "function") return toArray(order.get_orderlines());
    if (typeof order.getOrderlines === "function") return toArray(order.getOrderlines());
    return [];
}

function findLotByName(lotName) {
    if (!lotName || !STOCK_LOTS || !STOCK_LOTS.length) return null;

    // match exacto (tu prueba confirmó que funciona)
    const exact = STOCK_LOTS.find((l) => l?.name === lotName);
    if (exact) return exact;

    // fallback por si hubiera espacios/casing (opcional, por si acaso)
    const ln = String(lotName).trim().toUpperCase();
    return STOCK_LOTS.find((l) => String(l?.name || "").trim().toUpperCase() === ln) || null;
}

/**
 * Devuelve una “key” por color_code para comparar líneas.
 * - Si tiene 1 lote: "011m0155"
 * - Si tiene varios lotes: "011m0155|0ab123"
 * - Si no se puede resolver color_code: null
 */
function getLineColorCodeKey(line) {
    const packLots = toArray(line?.pack_lot_ids);
    if (!packLots.length) return null;

    const codes = [];
    for (const pl of packLots) {
        const lotName = getLotName(pl);
        if (!lotName) continue;

        const lot = findLotByName(lotName);
        const cc = lot?.color_code;
        if (cc) codes.push(String(cc).trim().toLowerCase());
    }

    if (!codes.length) return null;
    codes.sort();
    return codes.join("|");
}

patch(PosOrderline.prototype, {
    setUnitPrice(price) {

        const res = super.setUnitPrice(...arguments);

        const order = getOrderFromLine(this);
        if (!order) return res;

        // Anti-loop
        order.uiState = order.uiState || {};
        if (order.uiState.__idtx_sync_price_by_code_color) return res;

        const product = this.product || this.product_id;
        const myCode = getProductCode(product);
        if (!myCode) return res;

        const myColorKey = getLineColorCodeKey(this);

        // Si esta línea no tiene lotes o no se pudo resolver color -> no sync
        if (!myColorKey) return res;

        order.uiState.__idtx_sync_price_by_code_color = true;
        try {
            const lines = getOrderLines(order);

            for (const line of lines) {
                if (!line || line === this) continue;

                const p = line.product || line.product_id;
                const code = getProductCode(p);
                if (!code || code !== myCode) continue;

                const colorKey = getLineColorCodeKey(line);
                if (!colorKey) continue;

                // ✅ Misma regla: mismo producto + mismo color_code (aunque lot_name sea distinto)
                if (colorKey === myColorKey) {
                    line.setUnitPrice(price);
                }
            }
        } finally {
            order.uiState.__idtx_sync_price_by_code_color = false;
        }

        return res;
    },
});

