/** @odoo-module **/

import { TicketScreen } from "@point_of_sale/app/screens/ticket_screen/ticket_screen";
import { patch } from "@web/core/utils/patch";

patch(TicketScreen.prototype, {
    setup() {
        super.setup();
        this.state.filter = "SYNCED";
        this.state.search = { fieldName: "RECEIPT_NUMBER", searchTerm: "" };
        // No auto-seleccionar la orden activa al entrar a Órdenes: el detalle de la derecha
        // y el resumen quedan en blanco hasta que el cajero elija una orden manualmente.
        // (El core hace selectedOrderUuid = pos.getOrder()?.uuid, lo cual mostraba la orden actual.)
        this.state.selectedOrderUuid = null;
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
    },

    /*
     * Override getNumpadButtons: el botón "% Disc" del TicketScreen se traduce como
     * "% de descuento" en español y se ve recortado/extraño en el numpad. Forzamos "%".
     */
    getNumpadButtons() {
        const buttons = super.getNumpadButtons(...arguments);   // obtener la lista original
        const discBtn = buttons.find(b => b.value === "discount");
        if (discBtn) {
            discBtn.text = "%";                                  // forzar el símbolo corto
        }
        return buttons;
    },

    // ========================================================================
    // FLUJO DE REEMBOLSO: MARCADO PERSISTENTE POR ROLLO
    // ========================================================================
    // El POS estándar permite tener varios rollos con cantidad-a-reembolsar
    // simultáneamente (cada uno en order.uiState.lineToRefund[uuid].qty),
    // pero visualmente solo se ve el "seleccionado" (último clickeado).
    // Aquí añadimos:
    //   • isLineMarkedForRefund(line) → true si su qty > 0 (cualquier valor)
    //   • toggleLineRefundMark(line)  → marca/desmarca al hacer click en el checkbox
    //   • markAllForRefund()          → marca TODOS los rollos con cantidad completa
    //   • unmarkAllForRefund()        → desmarca todo (qty = 0)
    //   • getRefundQtyForLine(line)   → kilos a devolver, para mostrarlos en cada fila

    /**
     * Estado de devoluciones PREVIAS de una línea, para el sombreado de la fila:
     *   'total'   → el rollo ya se devolvió completo en NC anteriores (fila roja)
     *   'parcial' → se devolvió una parte y queda saldo (fila crema)
     *   false     → sin devoluciones previas (fila normal)
     * refundedQty ya excluye reembolsos cancelados (getter del core).
     */
    getLineRefundState(line) {
        if (!line) return false;
        const devuelto = line.refundedQty || 0;
        if (this.pos.isProductQtyZero(devuelto)) return false;
        const saldo = line.qty - devuelto;
        return (saldo <= 0 || this.pos.isProductQtyZero(saldo)) ? 'total' : 'parcial';
    },

    /**
     * ¿Esta línea tiene cantidad pendiente de reembolso (qty > 0)?
     * Usado por el XML para pintar el checkbox como marcado y resaltar la fila.
     */
    isLineMarkedForRefund(line) {
        const detail = line?.order_id?.uiState?.lineToRefund?.[line.uuid];
        // pos.isProductQtyZero usa la precisión decimal correcta (epsilon)
        return !!detail && !this.pos.isProductQtyZero(detail.qty);
    },

    /**
     * Cantidad de kilos a reembolsar para una línea (0 si no está marcada).
     * Se muestra al lado del checkbox para que el cajero la VEA al teclearla.
     */
    getRefundQtyForLine(line) {
        const detail = line?.order_id?.uiState?.lineToRefund?.[line.uuid];
        return detail ? (detail.qty || 0) : 0;
    },

    /**
     * Click en el checkbox de una fila: si está sin marcar, marca con la cantidad
     * COMPLETA del rollo (lo más común — devolver el rollo entero). Si ya estaba
     * marcado, desmarca (qty = 0).
     *
     * NO afecta la "selección" del orderline (eso lo sigue manejando onClickOrderline
     * del core), pero forzamos la selección a este line para que el numpad opere
     * sobre él inmediatamente — si el cajero quiere cambiar a una cantidad parcial,
     * solo teclea en el numpad sin tener que hacer otro click.
     */
    toggleLineRefundMark(line, ev) {
        // Evitar que el click propague al contenedor (que también selecciona la línea)
        if (ev) {
            ev.stopPropagation();
        }
        if (!line) return;

        // Seleccionar la línea para que el numpad apunte aquí
        const order = this.getSelectedOrder();
        if (order?.finalized) {
            this.state.selectedOrderlineIds[order.id] = line.id;
            this.numberBuffer.reset();                          // limpiar buffer numérico previo
        }

        // Obtener (o crear) el detalle de reembolso de esta línea
        const detail = this.getToRefundDetail(line);
        // Recalcular cuánto se PUEDE devolver (descuenta lo ya reembolsado en órdenes previas)
        detail.refundableQty = line.qty - line.refundedQty;

        if (this.isLineMarkedForRefund(line)) {
            // Ya marcada → desmarcar (qty=0)
            detail.qty = 0;
        } else {
            // Sin marcar → marcar con TODOS los kilos disponibles
            if (detail.refundableQty > 0) {
                detail.qty = detail.refundableQty;
            }
        }
    },

    /**
     * Botón "Marcar todos": pone qty = refundableQty en cada línea de la orden.
     * Caso de uso: cliente devuelve el pedido completo (todos los rollos).
     */
    markAllForRefund() {
        const order = this.getSelectedOrder();
        if (!order) return;
        for (const line of order.lines) {
            // Saltar líneas que no se pueden reembolsar (ya fueron devueltas o tienen destino)
            const detail = this.getToRefundDetail(line);
            if (detail.destionation_order_id) continue;          // ya enlazada a otra orden de reembolso
            detail.refundableQty = line.qty - line.refundedQty;  // recalcular tope
            if (detail.refundableQty > 0) {
                detail.qty = detail.refundableQty;
            }
        }
        this.numberBuffer.reset();                              // limpiar buffer numérico
    },

    /**
     * Botón "Quitar selección": pone qty = 0 en todas las líneas.
     */
    unmarkAllForRefund() {
        const order = this.getSelectedOrder();
        if (!order) return;
        for (const line of order.lines) {
            const detail = this.getToRefundDetail(line);
            detail.qty = 0;
        }
        this.numberBuffer.reset();
    },

    // ========================================================================
    // FIX: el core de Odoo POS pierde el pack_lot cuando la cantidad a devolver
    // es < 1 (devolución parcial de un rollo por peso, ej. 0.80 kg).
    // ========================================================================
    // En ticket_screen.js (core) línea ~351-353, el código construye los
    // pack_lots de la línea de reembolso así:
    //
    //   pack_lot_ids: options.slice(0, refundDetail.qty).map(...)
    //
    // El problema: `slice(0, 0.80)` en JavaScript trunca a 0 y devuelve [],
    // así que la línea de reembolso queda SIN lot. Cuando Odoo intenta
    // generar el picking de inventario, no encuentra un lot para asignar
    // a esos 0.80 kg y deja el picking en estado "assigned" pendiente.
    //
    // Solución: el hook `postRefund(destinationOrder)` se ejecuta JUSTO
    // después de que el core crea las líneas de reembolso, antes de navegar
    // al PaymentScreen. Aquí detectamos líneas con refunded_orderline_id
    // pero sin pack_lot_ids y les restauramos el lot desde la línea original.
    //
    // Para textil de Idetex cada línea tiene exactamente 1 rollo (1 lot),
    // así que copiamos todos los lots disponibles del original.
    postRefund(destinationOrder) {
        super.postRefund(destinationOrder);                                 // mantener cualquier lógica posterior
        if (!destinationOrder || !destinationOrder.lines) return;

        for (const refundLine of destinationOrder.lines) {
            // Solo nos interesan líneas que SON reembolsos y están sin lot
            if (!refundLine.refunded_orderline_id) continue;
            if (refundLine.pack_lot_ids && refundLine.pack_lot_ids.length > 0) continue;

            const original = refundLine.refunded_orderline_id;
            if (!original.pack_lot_ids || original.pack_lot_ids.length === 0) continue;

            // Calcular qué lots ya fueron devueltos en OTRAS órdenes confirmadas
            // (mismo cálculo que hace el core en su slice). Excluimos la propia
            // línea actual para no auto-excluirnos.
            const alreadyRefundedLots = original.refund_orderline_ids
                .filter(item => item.id !== refundLine.id
                                && !["cancel", "draft"].includes(item.order_id?.state))
                .flatMap(item => item.pack_lot_ids || [])
                .map(p => p.lot_name);

            // Lots aún disponibles para devolver de este rollo
            const availableLots = original.pack_lot_ids
                .map(p => p.lot_name)
                .filter(name => name && !alreadyRefundedLots.includes(name));

            // Crear los pack.operation.lot faltantes en la línea de reembolso.
            // Para textil cada línea tiene 1 sólo lot, así que normalmente
            // este bucle se ejecuta 1 vez. Sin restricción de slice(0,qty)
            // ya no perdemos el lot cuando qty es fraccional.
            for (const lotName of availableLots) {
                this.pos.models["pos.pack.operation.lot"].create({
                    pos_order_line_id: refundLine,                         // vincular a la línea de reembolso
                    lot_name: lotName,                                     // heredar nombre del rollo original
                });
            }
        }
    },

    /**
     * Total de kilos a devolver sumando todas las líneas marcadas.
     * Se muestra en la barra superior de la pantalla de reembolso.
     */
    get totalRefundKilos() {
        const order = this.getSelectedOrder();
        if (!order) return 0;
        let total = 0;
        for (const line of order.lines) {
            const detail = order.uiState?.lineToRefund?.[line.uuid];
            if (detail && !this.pos.isProductQtyZero(detail.qty)) {
                total += detail.qty;
            }
        }
        return total;
    },

    /**
     * Cantidad de líneas (rollos) marcadas para reembolso.
     */
    get totalRefundLines() {
        const order = this.getSelectedOrder();
        if (!order) return 0;
        return order.lines.filter(l => this.isLineMarkedForRefund(l)).length;
    },
});
