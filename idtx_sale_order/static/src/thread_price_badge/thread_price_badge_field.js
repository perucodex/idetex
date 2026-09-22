/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { usePopover } from "@web/core/popover/popover_hook";
import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { Component } from "@odoo/owl";

/**
 * Badge "N Hilos cotizados" en la cabecera de la cotización (JP, 21-sep-2026).
 * Campo: sale.order.thread_price_count. Al hacer clic muestra, por hilo,
 * código, nombre y fecha de última actualización de su regla en la lista de
 * precios (sale.order.thread_price_info, JSON).
 */
class ThreadPriceBadgePopover extends Component {
    static template = "idtx_sale_order.ThreadPriceBadgePopover";
    static props = {
        rows: Array,
        close: Function,
    };
}

class ThreadPriceBadgeField extends Component {
    static template = "idtx_sale_order.ThreadPriceBadgeField";
    static props = { ...standardFieldProps };

    setup() {
        this.popover = usePopover(ThreadPriceBadgePopover, { position: "bottom" });
    }

    get rows() {
        try {
            const rows = JSON.parse(this.props.record.data.thread_price_info || "[]");
            return Array.isArray(rows) ? rows : [];
        } catch {
            return [];
        }
    }

    get count() {
        return this.props.record.data[this.props.name] || this.rows.length;
    }

    get label() {
        return this.count === 1 ? _t("1 Hilo cotizado") : _t("%s Hilos cotizados", this.count);
    }

    get title() {
        return _t("Clic para ver la fecha de precio de cada hilo en la lista de precios");
    }

    onClick(ev) {
        if (this.rows.length) {
            this.popover.open(ev.currentTarget, { rows: this.rows });
        }
    }
}

export const threadPriceBadgeField = {
    component: ThreadPriceBadgeField,
    supportedTypes: ["integer"],
    fieldDependencies: [{ name: "thread_price_info", type: "text" }],
};

registry.category("fields").add("thread_price_badge", threadPriceBadgeField);
