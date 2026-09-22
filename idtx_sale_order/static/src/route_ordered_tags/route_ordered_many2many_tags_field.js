/** @odoo-module **/

import { registry } from "@web/core/registry";
import {
    Many2ManyTagsField,
    many2ManyTagsField,
} from "@web/views/fields/many2many_tags/many2many_tags_field";

/**
 * Etiquetas many2many ordenadas por la RUTA del análisis (JP, 22-sep-2026).
 * Odoo pinta un many2many en el orden del modelo relacionado (id); aquí las
 * Operaciones de la línea de venta se ordenan según sale.order.line.
 * route_operation_order (JSON con los ids de las fases en orden de secuencia),
 * aunque el usuario quite una y la vuelva a agregar. Las fases que ya no
 * están en la ruta van al final, en su orden original.
 */
export class RouteOrderedMany2ManyTagsField extends Many2ManyTagsField {
    get routeOrder() {
        try {
            const ids = JSON.parse(this.props.record.data.route_operation_order || "[]");
            return Array.isArray(ids) ? ids : [];
        } catch {
            return [];
        }
    }

    get tags() {
        const tags = super.tags;
        const order = this.routeOrder;
        if (!order.length) {
            return tags;
        }
        const rank = new Map(order.map((id, index) => [id, index]));
        const position = (tag, index) =>
            rank.has(tag.resId) ? rank.get(tag.resId) : order.length + index;
        return tags
            .map((tag, index) => ({ tag, key: position(tag, index) }))
            .sort((a, b) => a.key - b.key)
            .map((entry) => entry.tag);
    }
}

export const routeOrderedMany2ManyTagsField = {
    ...many2ManyTagsField,
    component: RouteOrderedMany2ManyTagsField,
    fieldDependencies: [{ name: "route_operation_order", type: "char" }],
};

registry.category("fields").add("route_ordered_many2many_tags", routeOrderedMany2ManyTagsField);
