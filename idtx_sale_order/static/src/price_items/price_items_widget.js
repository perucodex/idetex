/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
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
        // 1) Deserializa: {key: {"price": float, "label": str}}
        const raw = this.props.record.data.price_items || "{}";
        try {
            const dict = JSON.parse(raw);
            this.items = useState(
                Object.entries(dict).map(([k, v]) => ({
                    key: k,               // fijo, inglés
                    price: Number(v.price),
                    label: v.label        // traducible
                }))
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
        item.price = parseFloat(val) || 0;
        await this.recalculateDerivedItems();
    }

    async recalculateDerivedItems() {
        // 2) Filtra por claves FIJAS (inglés) → comparación fiable
        const baseItems = this.items.filter(item =>
            !["Weaving Loss", "Production Loss", "Financial Percentage", "Incoterm"].includes(item.key)
        );

        let total = baseItems.reduce((acc, it) => acc + (parseFloat(it.price) || 0), 0);

        const lineId = this.props.record.resId;
        const [lineData] = await this.orm.read("sale.order.line", [lineId], ["weaving_loss", "order_id"]);
        const scrap = lineData?.weaving_loss || 0;
        const [lineData1] = await this.orm.read("sale.order.line", [lineId], ["production_loss", "order_id"]);
        const prod_scrap = lineData1?.production_loss || 0;

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
            aux += loss;
            derived.push({
                key: "Weaving Loss",                         // fijo
                price: loss,
                label: _t("Weaving Loss: %s %", [(scrap * 100).toFixed(2)])
            });
        }

        if (prod_scrap) {
            const loss = round2(total * prod_scrap);
            aux += loss;
            derived.push({
                key: "Production Loss",                         // fijo
                price: loss,
                label: _t("Production Loss: %s %", [(prod_scrap * 100).toFixed(2)])
            });
        }

        if (financialPercentage) {
            const financial = round2(aux * financialPercentage);
            aux += financial;
            derived.push({
                key: "Financial Percentage",                    // fijo
                price: financial,
                label: _t("Financial Percentage: %s %", [(financialPercentage * 100).toFixed(2)])
            });
        }

        if (incotermPrice) {
            derived.push({
                key: "Incoterm",                                // fijo
                price: parseFloat(incotermPrice.toFixed(2)),
                label: _t("Incoterm: %s", [incotermCode])
            });
        }

        // 3) Reemplaza TODOS los items (claves fijas)
        this.items.splice(0, this.items.length,
            ...baseItems,
            ...derived.map(d => ({ key: d.key, price: d.price, label: d.label }))
        );
    }

    get total() {
        return this.items.reduce((acc, it) => acc + (parseFloat(it.price) || 0), 0);
    }

    save() {
        const dict = this.items.reduce((acc, it) => {
            acc[it.key] = { price: parseFloat(it.price) || 0, label: it.label };
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