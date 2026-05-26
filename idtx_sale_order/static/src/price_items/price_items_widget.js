/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { useService } from "@web/core/utils/hooks";
import { usePopover } from "@web/core/popover/popover_hook";
import { Component, useState } from "@odoo/owl";
import { standardWidgetProps } from "@web/views/widgets/standard_widget_props";
import { registry } from "@web/core/registry";

const round2 = (n) => Math.round((Number(n) + Number.EPSILON) * 100) / 100;

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
        this.hiddenItems = {};
        try {
            const dict = JSON.parse(raw);
            this.hiddenItems = Object.fromEntries(
                Object.entries(dict).filter(([k]) => k.startsWith("__"))
            );
            this.items = useState(
                Object.entries(dict)
                .filter(([k]) => !k.startsWith("__"))
                .map(([k, v]) => ({
                    key: k,               // fijo, inglés
                    price: round2(Number(v.price) || 0),
                    label: v.label,        // traducible
                    // Para hilos: costo por kilo (editable) y % de consumo
                    // (readonly). El price = cost_per_kilo * consumption_pct.
                    cost_per_kilo: Number(v.cost_per_kilo) || 0,
                    consumption_pct: Number(v.consumption_pct) || 0,
                    meta: v, // ← guarda todo
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
        item.price = round2(parseFloat(val) || 0);
        await this.recalculateDerivedItems();
    }

    async onCostPerKiloInput(ev, item) {
        let val = ev.target.value;
        val = val.replace(/,/g, "");
        val = val.replace(/[^0-9.]/g, "");
        val = val.replace(/^([^.]*\.)|\./g, (m, g1) => g1 || "");
        const newCost = parseFloat(val) || 0;
        item.cost_per_kilo = round2(newCost);
        // Recalcular el precio del hilo: cost_per_kilo * % consumo.
        item.price = round2(item.cost_per_kilo * (Number(item.consumption_pct) || 0));
        // Reflejar el cambio tambien en meta para que se persista al guardar.
        if (item.meta) {
            item.meta.cost_per_kilo = item.cost_per_kilo;
            item.meta.price = item.price;
        }
        await this.recalculateDerivedItems();
    }

    async recalculateDerivedItems() {
        const WEAV_LOSS_KEY = "Weaving Loss";
        const PROD_LOSS_KEY = "Production Loss";
        const FINANCIAL_KEY = "Financial Percentage";
        const INCOTERM_KEY  = "Incoterm";
        const baseItems = this.items.filter(it =>
            ![WEAV_LOSS_KEY, PROD_LOSS_KEY, FINANCIAL_KEY, INCOTERM_KEY].includes(it.key)
        );
        const sum = (arr) => arr.reduce((a, it) => a + (Number(it.price) || 0), 0);
        const lineId = this.props.record.resId;
        const [line] = await this.orm.read(
            "sale.order.line",
            [lineId],
            [
                "weaving_loss",
                "production_loss",
                "order_id",
                "is_weaving",
                "has_weaving_operation",
                "printing_design_id",
                "product_uom_qty",
                "min_qty",
            ]
        );
        const scrap = Number(line?.weaving_loss) || 0;
        const prod_scrap = Number(line?.production_loss) || 0;
        const isWeavingLine = !!(line?.has_weaving_operation || line?.is_weaving);
        let saleType = "";
        let financialPercentage = 0;
        let incotermPrice = 0;
        let incotermCode = "";
        if (line?.order_id?.[0]) {
            const [order] = await this.orm.read(
                "sale.order",
                [line.order_id[0]],
                ["payment_term_id", "incoterm", "sale_type"]
            );
            saleType = order?.sale_type || "";
            if (order?.payment_term_id?.[0]) {
                const [term] = await this.orm.read(
                    "account.payment.term",
                    [order.payment_term_id[0]],
                    ["financial_percentage"]
                );
                financialPercentage = Number(term?.financial_percentage) || 0;
            }
            if (order?.incoterm?.[0]) {
                const [inc] = await this.orm.read(
                    "account.incoterms",
                    [order.incoterm[0]],
                    ["unit_price", "code"]
                );
                incotermPrice = Number(inc?.unit_price) || 0;
                incotermCode = inc?.code || "";
            }
        }
        let total = round2(sum(baseItems));
        const thread_total = round2(sum(baseItems.filter(it => it.meta?.is_thread)));
        const derived = [];
        if (isWeavingLine && scrap) {
            const loss = round2(thread_total * scrap);
            total = round2(total + loss);
            derived.push({
                key: WEAV_LOSS_KEY,
                price: loss,
                label: _t("Weaving Loss: %s %", [(scrap * 100).toFixed(2)]),
                meta: {},
            });
        }
        if ( prod_scrap) {
            const loss = round2(total * prod_scrap);
            total = round2(total / (1 - prod_scrap));
            derived.push({
                key: PROD_LOSS_KEY,
                price: loss,
                label: _t("Production Loss: %s %", [(prod_scrap * 100).toFixed(2)]),
                meta: {},
            });
        }
        if (financialPercentage) {
            const financial = round2(total * financialPercentage);
            total = round2(total + financial);
            derived.push({
                key: FINANCIAL_KEY,
                price: financial,
                label: _t("Financial Percentage: %s %", [(financialPercentage * 100).toFixed(2)]),
                meta: {},
            });
        }
        if (incotermPrice) {
            derived.push({
                key: INCOTERM_KEY,
                price: round2(incotermPrice),
                label: _t("Incoterm: %s", [incotermCode]),
                meta: {},
            });
        }
        this.items.splice(0, this.items.length, ...baseItems, ...derived);
    }

    get total() {
        return this.items.reduce((acc, it) => acc + (parseFloat(it.price) || 0), 0);
    }

    async save() {
        await this.recalculateDerivedItems();
        const printing = this.items.find(it => it.key === "PRINTING");
        if (printing) {
            printing.meta = printing.meta || {};
            printing.meta.design_id = printing.meta.design_id ?? this.props.record.data.printing_design_id?.[0];
            printing.meta.qty = printing.meta.qty ?? this.props.record.data.product_uom_qty;
            printing.meta.min_qty = printing.meta.min_qty ?? this.props.record.data.min_qty;
            printing.label = printing.label || _t("PRINTING");
        }
        const dict = this.items.reduce((acc, it) => {
            acc[it.key] = { ...(it.meta || {}), price: round2(parseFloat(it.price) || 0), label: it.label };
            return acc;
        }, {});
        Object.assign(dict, this.hiddenItems || {});
        dict.__manual_override__ = true;
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
            [[record.resId]],
            { context: record.context }
        );
        await record.load();
    }
}

export const priceItemsWidget = {
    component: PriceItemsWidget,
};
registry.category("view_widgets").add("price_items_widget", priceItemsWidget);