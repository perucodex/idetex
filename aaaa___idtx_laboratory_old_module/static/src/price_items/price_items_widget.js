/** @odoo-module **/

import { useService } from "@web/core/utils/hooks";
import { usePopover } from "@web/core/popover/popover_hook";
import { Component, useState } from "@odoo/owl";
import { standardWidgetProps } from "@web/views/widgets/standard_widget_props";
import { registry } from "@web/core/registry";

// ---------- POPOVER ----------
class PriceItemsPopover extends Component {
    static template = "idtx_laboratory.PriceItemsPopover";
    static props = {
        record: Object,
        onSave: Function,
        close: Function,
    };

    setup() {
        const raw = this.props.record.data.price_items || "{}";
        try {
            const dict = JSON.parse(raw);
            this.items = useState(
                Object.entries(dict).map(([k, v]) => ({ key: k, value: Number(v) }))
            );
        } catch {
            this.items = useState([]);
        }

        this.orm = useService("orm");
        this.ui = useState({ readonly: false });

        this.orderData = useState({
            financial_percentage: 0,
            incoterm_unit_price: 0,
            incoterm_code: '',
            scrap: 0,
        });

        const orderId = this.props.record.data.order_id?.[0];
        if (orderId) {
            Promise.all([
                this.orm.read("sale.order", [orderId], ["payment_term_id", "incoterm", "state"]),
            ]).then(([orderRes]) => {
                const order = orderRes[0];
                this.ui.readonly = ["sale", "cancel"].includes(order?.state);

                if (order.payment_term_id) {
                    this.orm.read("account.payment.term", [order.payment_term_id[0]], ["financial_percentage"])
                        .then(term => {
                            this.orderData.financial_percentage = term[0]?.financial_percentage || 0;
                        });
                }

                if (order.incoterm) {
                    this.orm.read("account.incoterms", [order.incoterm[0]], ["unit_price", "code"])
                        .then(incoterm => {
                            this.orderData.incoterm_unit_price = incoterm[0]?.unit_price || 0;
                            this.orderData.incoterm_code = incoterm[0]?.code || '';
                        });
                }

                this.orderData.scrap = this.props.record.data.weaving_loss || 0;
            });
        }
    }

    async onNumberInput(ev, item) {
        let val = ev.target.value;
        val = val.replace(/,/g, "");
        val = val.replace(/[^0-9.]/g, "");
        val = val.replace(/^([^.]*\.)|\./g, (m, g1) => g1 || "");
        item.value = parseFloat(val) || 0;

        await this.recalculateDerivedItems();
    }

    async recalculateDerivedItems() {
        const baseItems = this.items.filter(item =>
            !item.key.startsWith("Production Loss") &&
            !item.key.startsWith("Financial Percentage") &&
            !item.key.startsWith("Incoterm")
        );

        let total = baseItems.reduce((acc, it) => acc + (parseFloat(it.value) || 0), 0);

        const lineId = this.props.record.resId;
        const [lineData] = await this.orm.read("sale.order.line", [lineId], ["weaving_loss", "order_id"]);
        const scrap = lineData?.weaving_loss || 0;

        let financialPercentage = 0;
        let incotermPrice = 0;
        let incotermCode = '';
        let aux = total;

        if (lineData?.order_id) {
            const [orderData] = await this.orm.read("sale.order", [lineData.order_id[0]], ["payment_term_id", "incoterm"]);
            
            if (orderData?.payment_term_id) {
                const [termData] = await this.orm.read("account.payment.term", [orderData.payment_term_id[0]], ["financial_percentage"]);
                financialPercentage = termData?.financial_percentage || 0;
            }

            if (orderData?.incoterm) {
                const [incotermData] = await this.orm.read("account.incoterms", [orderData.incoterm[0]], ["unit_price", "code"]);
                incotermPrice = incotermData?.unit_price || 0;
                incotermCode = incotermData?.code || '';
            }
        }

        const derived = [];

        const round2 = (num) => Math.round(num * 100) / 100;

        if (scrap) {
            const loss = round2(total * scrap);
            aux = aux + loss;
            derived.push({
                key: `Production Loss: ${(scrap * 100).toFixed(2)} %`,
                value: loss
            });
        }

        if (financialPercentage) {
            const financial = round2(aux * financialPercentage);
            aux = aux + financial
            derived.push({
                key: `Financial Percentage: ${(financialPercentage * 100).toFixed(2)} %`,
                value: financial
            });
        }

        if (incotermPrice) {
            derived.push({
                key: `Incoterm: ${incotermCode}`,
                value: parseFloat(incotermPrice.toFixed(2))
            });
        }

        this.items.splice(0, this.items.length, 
            ...baseItems,
            ...derived.map(d => ({ key: d.key, value: d.value }))
        );

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
        const jsonStr = JSON.stringify(dict);
        await record.update({ price_items: jsonStr });
        await this.orm.write(
            "sale.order.line",
            [record.resId],
            { price_items: jsonStr }
        );
        await this.orm.call(
            "sale.order.line",
            "js_compute_price_unit",
            [record.resId],
            { context: record.context }
        );
        await record.load();
    }
}

export const priceItemsWidget = {
    component: PriceItemsWidget,
};
registry.category("view_widgets").add("price_items_widget", priceItemsWidget);