import { PosStore } from "@point_of_sale/app/services/pos_store";
import { patch } from "@web/core/utils/patch";

patch(PosStore.prototype, {
    async processServerData() {
        await super.processServerData();
        
        this["stock.lot"] = await this.data.searchRead("stock.lot", []);
    },
});
