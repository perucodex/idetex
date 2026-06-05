/** @odoo-module **/

import { registry } from "@web/core/registry";
import { CharField, charField } from "@web/views/fields/char/char_field";
import { Component } from "@odoo/owl";

/**
 * Campo "Nombre de Color" en una sola columna:
 *  - Sin lab_dev_line_id  -> input editable (delega en el CharField estándar).
 *  - Con lab_dev_line_id   -> píldora/badge verde (aprobado) o rojo (pendiente).
 */
export class LabColorNameField extends Component {
    static template = "idtx_sale_order.LabColorNameField";
    static components = { CharField };
    static props = { ...CharField.props };

    get hasLabDev() {
        return !!this.props.record.data.lab_dev_line_id;
    }

    get value() {
        return this.props.record.data[this.props.name] || "";
    }

    get badgeClass() {
        return this.props.record.data.has_approved_lab_line
            ? "text-bg-success"
            : "text-bg-danger";
    }
}

export const labColorNameField = {
    ...charField,
    component: LabColorNameField,
};

registry.category("fields").add("lab_color_name", labColorNameField);
