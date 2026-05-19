/** @odoo-module **/

import { PosStore } from "@point_of_sale/app/services/pos_store";
import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";

patch(PosStore.prototype, {
    async setup() {
        await super.setup(...arguments);
        this.numpadMode = "price";
    },

    selectOrderLine(order, line) {
        super.selectOrderLine(...arguments);
        this.numpadMode = "price";
    },

    /*
     * Override clickSaveOrder: el original no hace await del syncAllOrders, así que cuando termina
     * los hooks del servidor pueden no haber terminado. Aquí hacemos await explícito antes de
     * refrescar el stock, para que los rollos reservados aparezcan bloqueados de inmediato.
     */
    async clickSaveOrder() {
        // Esperar a que el servidor procese la orden (dispara nuestros hooks server-side de reserva)
        await this.syncAllOrders({ orders: [this.getOrder()] });
        // Notificación al cajero
        this.notification.add(_t("Order saved for later"), { type: "success" });
        // Crear una orden vacía nueva para continuar atendiendo
        this.setOrder(this.getEmptyOrder());
        this.mobile_pane = "right";
        // Refrescar el modelo de stock para reflejar las nuevas reservas (rollos en rojo con 🔒).
        // En background para no bloquear la UI; si falla solo loggeamos.
        this.refreshStockData().catch(e => console.error('IDTX: Stock refresh tras guardar falló:', e));
    },

    /*
     * Override afterOrderDeletion: cuando se elimina/cancela un pedido (desde Órdenes o desde el
     * menú "Cancelar Pedido"), el backend libera los rollos (state='cancel' → hook write libera).
     * Aquí refrescamos el stock en el frontend para que los rollos liberados vuelvan a aparecer
     * disponibles sin necesidad de tocar manualmente "Actualizar Stock".
     */
    async afterOrderDeletion() {
        // Ejecutar la lógica original primero (selecciona la siguiente orden, etc.)
        const result = await super.afterOrderDeletion(...arguments);
        // Refrescar el stock en background: el servidor ya liberó las reservas (state cambió a 'cancel').
        this.refreshStockData().catch(e => console.error('IDTX: Stock refresh tras eliminar falló:', e));
        return result;
    },

    // Recarga el modelo idtx.pos.stock.report desde el servidor y actualiza la memoria del POS.
    // Elimina los lotes que ya no tienen stock (excluidos por HAVING SUM >= 0 en la vista SQL).
    async refreshStockData() {
        const fields = [                    // campos definidos en _load_pos_data_fields
            'id', 'product_id', 'product_name', 'product_code', 'product_label',
            'lot_id', 'lot_name', 'partida', 'partida_label', 'roll_id', 'roll_name',
            'color_code', 'color_name', 'quantity', 'location_id', 'write_date',
            'is_reserved', 'reserved_by_order_id',  // campos de bloqueo por reserva POS
        ];
        // Campos Many2one que search_read devuelve como [id, "nombre"] — hay que normalizar a solo el entero.
        // loadConnectedData almacena el valor tal cual en RAW_SYMBOL; si llega como array,
        // el getter many2one intenta getById(array) y no encuentra el registro relacionado.
        const many2oneFields = ['product_id', 'lot_id', 'roll_id', 'location_id', 'reserved_by_order_id'];
        try {
            // Obtener todos los registros actuales del servidor (recarga completa del modelo de stock)
            const rawRecords = await this.data.orm.searchRead(
                'idtx.pos.stock.report',    // modelo de vista SQL
                [],                          // sin dominio: traer todos los lotes disponibles
                fields
            );

            // Normalizar campos Many2one: convertir [id, "nombre"] → id (entero)
            const freshRecords = rawRecords.map(r => {
                const clean = { ...r };
                for (const f of many2oneFields) {
                    if (Array.isArray(clean[f])) {
                        clean[f] = clean[f][0];     // extraer solo el ID numérico
                    }
                }
                return clean;
            });

            const stockModel = this.models['idtx.pos.stock.report'];   // referencia al modelo en memoria
            const freshIds = new Set(freshRecords.map(r => r.id));     // IDs actuales del servidor

            // Eliminar del modelo en memoria los lotes que ya no existen en el servidor (agotados)
            for (const record of stockModel.getAll()) {
                if (!freshIds.has(record.id)) {
                    stockModel.delete(record);                          // quita el lote de la tabla
                }
            }

            // Actualizar o insertar los registros frescos en el modelo en memoria
            this.models.loadConnectedData({ 'idtx.pos.stock.report': freshRecords });

        } catch (e) {
            console.error('IDTX: Error al actualizar stock:', e);      // log de error sin interrumpir el POS
        }
    },
});
