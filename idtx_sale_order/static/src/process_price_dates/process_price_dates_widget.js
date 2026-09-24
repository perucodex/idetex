/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { usePopover } from "@web/core/popover/popover_hook";
import { registry } from "@web/core/registry";
import { standardWidgetProps } from "@web/views/widgets/standard_widget_props";
import { Component } from "@odoo/owl";

/**
 * Fechas de precio de los procesos de la línea (JP, 23-sep-2026).
 * Widget del VENDEDOR: ocupa el lugar del "Editar precios" (solo admin de
 * ventas) y muestra, por proceso cotizado, la fecha de última actualización
 * de su precio, sin importes, sin hilado y sin mermas.
 * Datos: sale.order.line.process_price_info (JSON calculado en el servidor).
 */
class ProcessPriceDatesPopover extends Component {
    static template = "idtx_sale_order.ProcessPriceDatesPopover";
    static props = {
        rows: Array,
        close: Function,
    };
}

class ProcessPriceDatesWidget extends Component {
    static template = "idtx_sale_order.ProcessPriceDatesWidget";
    static props = { ...standardWidgetProps };

    setup() {
        this.popover = usePopover(ProcessPriceDatesPopover, { position: "top" });
    }

    get rows() {
        try {
            const rows = JSON.parse(this.props.record.data.process_price_info || "[]");
            return Array.isArray(rows) ? rows : [];
        } catch {
            return [];
        }
    }

    get hasMissing() {
        return this.rows.some((row) => !row.has_price);
    }

    get title() {
        return this.hasMissing
            ? _t("Hay procesos sin precio. Clic para ver la fecha de precio de cada proceso")
            : _t("Clic para ver la fecha de última actualización del precio de cada proceso");
    }

    onClick(ev) {
        if (this.rows.length) {
            this.popover.open(ev.currentTarget, { rows: this.rows });
        }
    }
}

export const processPriceDatesWidget = {
    component: ProcessPriceDatesWidget,
};

registry.category("view_widgets").add("process_price_dates_widget", processPriceDatesWidget);
