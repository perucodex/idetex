/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { Component } from "@odoo/owl";
import { standardWidgetProps } from "@web/views/widgets/standard_widget_props";
import { registry } from "@web/core/registry";

/**
 * Semáforo de producción del producto en la línea del pedido (JP, 21-sep-2026).
 * Lee sale.order.line.analysis_production_indicator (estado a nivel de
 * ANÁLISIS + OF existentes):
 *   none        → círculo rojo sin letra (ninguna OF de muestra/piloto)
 *   sample      → rojo con M (muestra en curso)
 *   sample_done → verde con M (muestra terminada)
 *   pilot       → naranja con P (piloto en curso, aún sin terminar)
 *   pilot_done  → verde con P (piloto terminado: se puede confirmar venta)
 *   production  → verde sin letra (OF de venta o servicio terminada)
 */
class AnalysisProductionStateWidget extends Component {
    static template = "idtx_sale_order.AnalysisProductionStateWidget";
    static props = { ...standardWidgetProps };

    get states() {
        return {
            none: {
                cls: "o_analysis_prod_state--red",
                letter: "",
                title: _t("Sin OF: el producto nunca se ha fabricado (falta muestra/piloto)"),
            },
            sample: {
                cls: "o_analysis_prod_state--red",
                letter: "M",
                title: _t("Muestra en curso: falta terminarla"),
            },
            sample_done: {
                cls: "o_analysis_prod_state--green",
                letter: "M",
                title: _t("Muestra terminada: aún no hay piloto"),
            },
            pilot: {
                cls: "o_analysis_prod_state--orange",
                letter: "P",
                title: _t("Piloto en curso: falta terminarlo para confirmar la OF de venta"),
            },
            pilot_done: {
                cls: "o_analysis_prod_state--green",
                letter: "P",
                title: _t("Piloto terminado: se puede confirmar la OF de venta o servicio"),
            },
            production: {
                cls: "o_analysis_prod_state--green",
                letter: "",
                title: _t("En producción: ya tiene OF de venta o servicio terminada"),
            },
        };
    }

    get state() {
        const data = this.props.record?.data;
        // La visibilidad se decide aquí: un <widget> de lista no respeta
        // column_invisible con expresiones de parent. Se muestra en
        // cotización y pedido, solo en líneas de tejido de empresa productora.
        if (!data || !data.is_weaving || !data.parent_is_company_produce) {
            return null;
        }
        return this.states[data.analysis_production_indicator] || this.states.none;
    }
}

export const analysisProductionStateWidget = {
    component: AnalysisProductionStateWidget,
    fieldDependencies: [
        { name: "is_weaving", type: "boolean" },
        { name: "parent_is_company_produce", type: "boolean" },
    ],
};

registry.category("view_widgets").add("analysis_production_state_widget", analysisProductionStateWidget);
