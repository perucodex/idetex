/** @odoo-module **/

import { useService } from "@web/core/utils/hooks";
import { usePopover } from "@web/core/popover/popover_hook";
import { Component, useState } from "@odoo/owl";
import { standardWidgetProps } from "@web/views/widgets/standard_widget_props";
import { registry } from "@web/core/registry";
import { useRecordObserver } from "@web/model/relational_model/utils";

// ---------- POPOVER ----------
class PriceItemsPopover extends Component {
    static template = "idtx_laboratory.PriceItemsPopover";
    static props = {
        record: Object,
        onSave: Function,
        close: Function,
    };

    setup() {
        const raw = this.props.record.data.price_items || "{}";  // diccionario plano
        try {
            const dict = JSON.parse(raw);
            this.items = useState(
                Object.entries(dict).map(([k, v]) => {
                    return { key: k, value: Number(v) };
                })
            );
        } catch {
            this.items = useState([]);
        }

        this.orm = useService("orm");
        this.ui = useState({ readonly: false });

        // ---- id del pedido (order_id) ----
        const orderId = this.props.record.data.order_id?.[0];  // many2one -> [id, name]
        if (orderId) {
            this.orm.read("sale.order", [orderId], ["state"])
                .then((res) => {
                    this.ui.readonly = ["sale", "cancel"].includes(res[0]?.state);
                });
        }
    }

    onNumberInput(ev, item) {
        let val = ev.target.value;
        val = val.replace(/,/g, "");
        val = val.replace(/[^0-9.]/g, "");
        val = val.replace(/^([^.]*\.)|\./g, (m, g1) => g1 || "");
        item.value = val;
    }

    get total() {
        return this.items.reduce((acc, it) => acc + (parseFloat(it.value) || 0), 0);
    }

    save() {
        const dict = this.items.reduce((acc, it) => {
            acc[it.key] = parseFloat(it.value) || 0;
            return acc;
        }, {});
        this.props.onSave(dict);
        this.props.close();
    }

}

// ---------- WIDGET ----------
class PriceItemsWidget extends Component {
    static components = { Popover: PriceItemsPopover };
    static template = "idtx_laboratory.PriceItemsWidget";
    static props = { ...standardWidgetProps };

    setup() {
        this.popover = usePopover(PriceItemsPopover, { position: "top" });
        this.orm = useService("orm");
    }

    showPopover(ev) {
        this.popover.open(ev.currentTarget, {
            record: this.props.record,
            onSave: (dict) => this._onSave(dict),
        });
    }

    async _onSave(dict) {
        const record = this.props.record;
        await record.update({ price_items: JSON.stringify(dict) });
        const total = Object.values(dict).reduce((acc, v) => acc + (parseFloat(v) || 0), 0);
        await record.update({ price_unit: total });
    }
}

export const priceItemsWidget = {
    component: PriceItemsWidget,
};
registry.category("view_widgets").add("price_items_widget", priceItemsWidget);
