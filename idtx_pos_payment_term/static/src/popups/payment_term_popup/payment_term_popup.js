import { _t } from "@web/core/l10n/translation";
import { Component, useState, useRef, onMounted } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";

export class PaymentTermPopup extends Component {
    static template = "idtx_pos_payment_term.PaymentTermPopup";
    static components = { Dialog };
    static props = {
        title: { type: String, optional: true },
        terms: Array,
        selectedId: { type: [Number, { value: false }], optional: true },
        getPayload: Function,
        close: Function,
    };
    static defaultProps = {
        title: _t("Seleccione el termino de pago"),
        selectedId: false,
    };

    setup() {
        this.state = useState({ query: "" });
        this.searchRef = useRef("search");
        onMounted(() => this.searchRef.el?.focus());
    }

    get filteredTerms() {
        const q = this.state.query.trim().toLowerCase();
        if (!q) {
            return this.props.terms;
        }
        return this.props.terms.filter((t) =>
            (t.name || "").toLowerCase().includes(q)
        );
    }

    selectTerm(term) {
        this.props.getPayload(term);
        this.props.close();
    }
}
