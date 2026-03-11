/** @odoo-module */

import { OrderDisplay } from "@point_of_sale/app/components/order_display/order_display";
import { patch } from "@web/core/utils/patch";

/*
 * Clase auxiliar para representar un Grupo de Líneas.
 * Imita la interfaz mínima necesaria para que el loop de renderizado funcione.
 */
class IDTXGroupLines {
    constructor(key, lines) {
        this.isGroup = true;
        this.key = key;
        this.children = lines || [];
        this.uuid = key; // Use key as UUID for rendering keys
    }

    get key_name() {
        const first = this.children[0];
        if (!first) return this.key;
        const name = first.product_id.display_name || first.product_id.name || "Producto Desconocido";
        const color = first.color_name || "Sin Color";
        return `${name} - ${color}`;
    }

    /*
     * Retorna la suma del precio total de todas las líneas.
     */
    get displayPrice() {
        return this.children.reduce((acc, line) => acc + (line.displayPrice || 0), 0);
    }

    /*
     * Retorna el precio unitario promedio (o del primer hijo si son iguales).
     */
    get displayPriceUnit() {
        const first = this.children[0];
        return first ? first.displayPriceUnit : 0;
    }

    /*
     * Helper para mockear getQuantity (no usado directamente en UI grupo pero por seguridad)
     */
    getQuantity() {
        return this.children.reduce((acc, l) => acc + l.getQuantity(), 0);
    }

    getQuantityStr() {
        return this.getQuantity().toFixed(2) + " Kg";
    }

    /*
     * Manejo de click en hijos (proxy)
     */
    onChildClick(ev, line) {
        // Nada especial, el evento bubbulea o se maneja en Orderline
    }

    get selected() {
        return this.children.some(l => l.selected);
    }
}

patch(OrderDisplay, {
    props: {
        ...OrderDisplay.props,
        detailed: { type: Boolean, optional: true },
    }
});

patch(OrderDisplay.prototype, {
    /*
     * Sobreescribimos comboSortedLines para devolver GRUPOS en lugar de líneas planas.
     * NOTA: Esto cambia lo que recibe el template y los slots.
     */
    get comboSortedLines() {
        // Obtenemos las líneas planas originales (incluyendo lógica combo)
        const flatLines = super.comboSortedLines;

        if (flatLines.length === 0) return [];

        // LÓGICA CONDICIONAL:
        // Si estamos en modo recibo Y se pidió detallado -> Devolvemos plano.
        // En modo display (carrito) siempre agrupamos.
        if (this.props.mode === 'receipt' && this.props.detailed) {
            return flatLines;
        }

        const groups = {};
        const result = [];

        for (const line of flatLines) {
            // Clave de agrupación: Código + Color
            // Si no tiene color, usamos solo el código (o ID de producto).
            const code = line.product_id.default_code || "N/A";
            const color = line.color_name ? line.color_name.trim().toUpperCase() : "__NO_COLOR__";

            // Solo agrupamos si hay color (regla de negocio implícita? o siempre?)
            // El usuario pidió "Codigo + Nombre del color".
            // Si es "__NO_COLOR__", ¿lo dejamos suelto o lo agrupamos por producto?
            // Vamos a agrupar siempre por Producto + Color.

            const key = `${line.product_id.id}_${color}`;

            if (!groups[key]) {
                const group = new IDTXGroupLines(key, []);
                groups[key] = group;
                result.push(group);
            }
            groups[key].children.push(line);
        }

        return result;
    }
});
