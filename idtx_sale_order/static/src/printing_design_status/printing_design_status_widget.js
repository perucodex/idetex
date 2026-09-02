/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { usePopover } from "@web/core/popover/popover_hook";
import { Component } from "@odoo/owl";
import { standardWidgetProps } from "@web/views/widgets/standard_widget_props";
import { registry } from "@web/core/registry";

function getPrintingDesignId(record) {
    const value = record?.data?.printing_design_id;
    if (Array.isArray(value)) {
        return value[0] || null;
    }
    if (value && typeof value === "object") {
        if (typeof value.resId === "number") {
            return value.resId;
        }
        if (typeof value.id === "number") {
            return value.id;
        }
        if (Array.isArray(value.currentIds) && value.currentIds.length) {
            return value.currentIds[0];
        }
        if (Array.isArray(value.resIds) && value.resIds.length) {
            return value.resIds[0];
        }
        return null;
    }
    return typeof value === "number" ? value : null;
}

function getPrintingDesignName(record) {
    const value = record?.data?.printing_design_id;
    if (Array.isArray(value) && value[1]) {
        return value[1];
    }
    if (value && typeof value === "object") {
        return value.displayName || value.name || record?.data?.printing_design_name || null;
    }
    return record?.data?.printing_design_name || null;
}

class PrintingDesignStatusPopover extends Component {
    static template = "idtx_sale_order.PrintingDesignStatusPopover";
    static props = {
        record: Object,
        close: Function,
    };

    get hasDesign() {
        return Boolean(getPrintingDesignId(this.props.record));
    }

    get designName() {
        return getPrintingDesignName(this.props.record) || _t("No design selected");
    }

    get previewSrc() {
        const designId = getPrintingDesignId(this.props.record);
        return designId
            ? `/web/image?model=printing.design&id=${designId}&field=preview_image`
            : null;
    }

    get noPreviewMessage() {
        return _t("The selected design has no preview image.");
    }

    get emptyMessage() {
        return _t("Select a design to preview its image.");
    }
}

class PrintingDesignStatusWidget extends Component {
    static template = "idtx_sale_order.PrintingDesignStatusWidget";
    static props = { ...standardWidgetProps };

    setup() {
        this.popover = usePopover(PrintingDesignStatusPopover, { position: "top" });
    }

    get hasDesign() {
        return Boolean(getPrintingDesignId(this.props.record));
    }

    get isVisible() {
        const data = this.props.record?.data;
        if (!data || data.parent_is_quote || !data.parent_is_company_produce) {
            return false;
        }
        // Solo en líneas que llevan estampado: en las demás el punto no
        // significaba nada y se leía como un dato faltante.
        return Boolean(data.is_printing) || Boolean(getPrintingDesignId(this.props.record));
    }

    get dotClass() {
        return this.hasDesign
            ? "o_printing_design_status_dot o_printing_design_status_dot--ok"
            : "o_printing_design_status_dot o_printing_design_status_dot--missing";
    }

    get title() {
        return this.hasDesign ? _t("Show design preview") : _t("No printing design selected");
    }

    showPopover(ev) {
        this.popover.open(ev.currentTarget, {
            record: this.props.record,
        });
    }
}

export const printingDesignStatusWidget = {
    component: PrintingDesignStatusWidget,
    // El punto solo se muestra en líneas de estampado: se declaran los campos
    // que decide la visibilidad para no depender de que estén en la vista.
    fieldDependencies: [
        { name: "is_printing", type: "boolean" },
        { name: "printing_design_id", type: "many2one", relation: "printing.design" },
    ],
};

registry.category("view_widgets").add("printing_design_status_widget", printingDesignStatusWidget);
