/** @odoo-module **/
import { PosOrderline } from "@point_of_sale/app/models/pos_order_line";
import { patch } from "@web/core/utils/patch";

patch(PosOrderline.prototype, {
    get lotColorName() {
        if (!this.pack_lot_ids?.length) return "";
        const lotName = this.pack_lot_ids[0].lot_name;
        if (!lotName || !this.models) return "";
        const lot = (this.models["stock.lot"] || []).find(l =>
            l.name === lotName
        );
        if (!lot) return "";
        return (lot?.color_code && lot?.color_name)
            ? `[${lot.color_code}] ${lot.color_name}`
            : "";
    },
});