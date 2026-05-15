/** @odoo-module **/

import { TicketScreen } from "@point_of_sale/app/screens/ticket_screen/ticket_screen";
import { patch } from "@web/core/utils/patch";

patch(TicketScreen.prototype, {
    setup() {
        super.setup();
        this.state.filter = "SYNCED";
        this.state.search = { fieldName: "RECEIPT_NUMBER", searchTerm: "" };
    },
    async reprintInvoice(order) {
        if (!order) return;
        try {
            // Intentar obtener el ID del movimiento contable (factura)
            let accountMoveId = order.account_move?.id || (order.raw && order.raw.account_move);
            
            // Si no está en memoria, forzar carga desde el servidor
            if (!accountMoveId) {
                const orders = await this.pos.data.loadServerOrders([["id", "=", order.id]]);
                if (orders && orders.length > 0) {
                    accountMoveId = orders[0].raw.account_move;
                }
            }

            if (accountMoveId) {
                await this.pos.env.services.account_move.downloadPdf(accountMoveId);
            } else {
                // Si la orden no tiene factura asociada, intentar generarla
                await this.pos.data.call("pos.order", "action_pos_order_invoice", [order.id]);
                const orders = await this.pos.data.loadServerOrders([["id", "=", order.id]]);
                if (orders && orders.length > 0 && orders[0].raw.account_move) {
                    await this.pos.env.services.account_move.downloadPdf(orders[0].raw.account_move);
                }
            }
        } catch (error) {
            console.error("Error al reimprimir factura:", error);
        }
    },
    get totalKilos() {
        const order = this.getSelectedOrder();
        if (!order) return 0;
        return order.getOrderlines().reduce((acc, line) => acc + line.getQuantity(), 0);
    },
    /**
     * Calcula el total de rollos de la orden seleccionada
     */
    get totalRolls() {
        const order = this.getSelectedOrder();
        if (!order) return 0;
        return order.getOrderlines().length;
    }
});
