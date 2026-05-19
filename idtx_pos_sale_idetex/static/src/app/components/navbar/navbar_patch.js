/** @odoo-module **/

import { Navbar } from "@point_of_sale/app/components/navbar/navbar";
import { patch } from "@web/core/utils/patch";

patch(Navbar.prototype, {
    // Llama al método refreshStockData del PosStore para recargar los datos de stock
    async refreshStockData() {
        await this.pos.refreshStockData();          // el método está en pos_store_patch.js
    },
});
