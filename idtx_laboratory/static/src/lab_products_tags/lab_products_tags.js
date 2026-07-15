/** @odoo-module */

import { registry } from "@web/core/registry";
import {
    many2ManyTagsField,
    Many2ManyTagsField,
} from "@web/views/fields/many2many_tags/many2many_tags_field";

/**
 * Tags de productos de la línea de Lab Dev coloreados por aprobación de
 * receta: VERDE si el producto tiene una receta aprobada en la línea,
 * ROJO si aún no. Lee los aprobados del campo (invisible en la vista)
 * `approved_product_ids` del registro.
 */
export class LabProductsApprovalTags extends Many2ManyTagsField {
    getTagProps(record) {
        const props = super.getTagProps(record);
        const approved = this.props.record.data.approved_product_ids;
        const approvedIds = (approved && (approved.currentIds || approved.resIds)) || [];
        // Paleta estándar de tags Odoo: 10 = verde, 1 = rojo.
        props.colorIndex = approvedIds.includes(record.resId) ? 10 : 1;
        return props;
    }
}

export const labProductsApprovalTags = {
    ...many2ManyTagsField,
    component: LabProductsApprovalTags,
};

registry.category("fields").add("lab_products_approval_tags", labProductsApprovalTags);
