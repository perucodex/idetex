/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { onWillStart } from "@odoo/owl";
import { SelectScaleDialog } from "./select_scale_dialog";

/**
 * Diálogo de tallas de rectilíneos: HEREDA todo el comportamiento del diálogo
 * de balanza (opciones con filtrado de empleados/equipos, lectura de peso en
 * vivo, peso manual con autorización, persistencia de selección) y agrega
 * Talla + Cantidad. El rectilíneo registra cantidad Y peso.
 */
export class SelectSizeDialog extends SelectScaleDialog {
    static template = "idtx_mrp_shop.SelectSizeDialog";
    static props = {
        ...SelectScaleDialog.props,
        sizes: { type: Array, optional: true },
        selectedSize: { type: [Number, String], optional: true },
    };

    setup() {
        super.setup();
        this.state.sizes = this.props.sizes || [];
        this.state.selectedSize = this.props.selectedSize ? String(this.props.selectedSize) : "";
        this.state.quantity = 1;
        onWillStart(async () => {
            if (!this.state.sizes.length) {
                await this._loadSizes();
            }
            this._restoreSizeSelection();
        });
    }

    // La talla también se recuerda (último roll vía props + localStorage,
    // igual que opción/empleado/equipo del padre).
    _restoreSizeSelection() {
        const validIds = new Set((this.state.sizes || []).map((s) => String(s.id)));
        if (this.state.selectedSize && !validIds.has(String(this.state.selectedSize))) {
            this.state.selectedSize = "";
        }
        if (!this.state.selectedSize) {
            try {
                const raw = window.localStorage.getItem(this._getLSKey());
                const parsed = raw ? JSON.parse(raw) : {};
                if (parsed.size_id && validIds.has(String(parsed.size_id))) {
                    this.state.selectedSize = String(parsed.size_id);
                }
            } catch (e) {
                // ignore
            }
        }
    }

    _persistSizeSelection() {
        try {
            const key = this._getLSKey();
            const raw = window.localStorage.getItem(key);
            const parsed = raw ? JSON.parse(raw) : {};
            if (this.state.selectedSize) {
                parsed.size_id = String(this.state.selectedSize);
            }
            window.localStorage.setItem(key, JSON.stringify(parsed));
        } catch (e) {
            // ignore
        }
    }

    async _loadSizes() {
        const workorderId = this._getWorkorderId();
        if (!workorderId) {
            this.state.sizes = [];
            return;
        }
        const result = await this.ormService.call(
            "mrp.workorder",
            "get_available_sizes",
            [workorderId]
        );
        this.state.sizes = result || [];
        if (!this.state.sizes.length) {
            this.notification.add(
                _t("No sizes on technical sheet of the product."),
                { type: "danger" }
            );
        }
    }

    get isConfirmEnabled() {
        return (
            super.isConfirmEnabled &&
            !!this.state.selectedOption &&
            !!this.state.selectedSize &&
            Number(this.state.quantity) > 0
        );
    }

    get isSizeInvalid() {
        return this.state.triedConfirm && !this.state.selectedSize;
    }

    get isQuantityInvalid() {
        return this.state.triedConfirm && !(Number(this.state.quantity) > 0);
    }

    _getConfirmPayload(w) {
        return {
            ...super._getConfirmPayload(w),
            size: this.state.selectedSize,
            quantity: Number(this.state.quantity),
        };
    }

    confirm() {
        this.state.triedConfirm = true;
        // Validaciones propias del registro por talla; el resto (empleado,
        // equipo, peso balanza/manual) las hace el padre.
        if (!this.state.selectedOption) {
            this.notification.add(_t("You must select an option."), { type: "danger" });
            return;
        }
        if (!this.state.selectedSize) {
            this.notification.add(_t("You must select a size."), { type: "danger" });
            return;
        }
        if (!(Number(this.state.quantity) > 0)) {
            this.notification.add(_t("You must enter a valid quantity."), { type: "danger" });
            return;
        }
        this._persistSizeSelection();
        return super.confirm();
    }
}
