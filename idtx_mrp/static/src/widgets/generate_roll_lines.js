import { Component } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { x2ManyCommands } from "@web/core/orm_service";
import { getId } from "@web/model/relational_model/utils";
import { standardWidgetProps } from "@web/views/widgets/standard_widget_props";

/**
 * Botón "Generar" de la recepción de rollos del cliente (mrp.roll.reception).
 *
 * Agrega N filas con el peso promedio y la referencia del cliente correlativa
 * (generate_ref_start = "A1" → A1, A2, A3...; se incrementa el número final y se
 * conserva el relleno de ceros) directamente en el formulario, igual que
 * el widget "Generar lotes/series" de inventario (stock/widgets/generate_serial.js):
 * NO guarda el registro ni cierra el diálogo; las filas se persisten al pulsar
 * Guardar / Recibir. Un <button type="object"> guardaba la recepción en
 * borrador y cerraba el modal (JP, 10-sep-2026).
 */
export class GenerateRollLines extends Component {
    static template = "idtx_mrp.GenerateRollLines";
    static props = { ...standardWidgetProps };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
    }

    get disabled() {
        return this.props.readonly || this.props.record.data.state !== "draft";
    }

    /**
     * "A1" → ["A1","A2",...], next "A6"; "R-007" → R-008...; "R" (sin número)
     * → R1, R2...; vacío → referencias en blanco.
     */
    nextRefs(start, count) {
        start = (start || "").trim();
        if (!start) {
            return { list: Array(count).fill(false), next: "" };
        }
        const m = /^(.*?)(\d+)$/.exec(start);
        const prefix = m ? m[1] : start;
        const first = m ? parseInt(m[2], 10) : 1;
        const width = m ? m[2].length : 0;
        const fmt = (n) => prefix + String(n).padStart(width, "0");
        const list = [];
        for (let i = 0; i < count; i++) {
            list.push(fmt(first + i));
        }
        return { list, next: fmt(first + count) };
    }

    async onClick() {
        const record = this.props.record;
        const count = parseInt(record.data.generate_count) || 0;
        const weight = record.data.generate_weight || 0;
        if (count <= 0) {
            this.notification.add(_t("Indica cuántos rollos generar."), { type: "warning" });
            return;
        }
        const lines = record.data.line_ids;
        const fieldNames = Object.keys(lines.activeFields);
        // Valores por defecto del servidor para todas las columnas visibles, así
        // cada fila nace completa sin disparar un onchange por fila.
        const defaults = await this.orm.call(lines.resModel, "default_get", [fieldNames], {
            context: lines.context,
        });
        let seq = Math.max(0, ...lines.records.map((r) => r.data.sequence || 0));
        const refs = this.nextRefs(record.data.generate_ref_start, count);
        const newLines = [];
        for (let i = 0; i < count; i++) {
            const values = {};
            for (const name of fieldNames) {
                const field = lines.fields[name];
                let value = name in defaults ? defaults[name] : false;
                if (field.type === "one2many" || field.type === "many2many") {
                    value = value || [];
                } else if (field.type === "many2one" && typeof value === "number") {
                    value = { id: value, display_name: "" };
                }
                values[name] = value;
            }
            values.sequence = ++seq;
            values.customer_roll_ref = refs.list[i];
            values.declared_weight = weight;
            newLines.push(
                lines._createRecordDatapoint(values, {
                    mode: "readonly",
                    virtualId: getId("virtual"),
                    manuallyAdded: false,
                })
            );
        }
        lines.records.push(...newLines);
        lines._commands.push(...newLines.map((r) => [x2ManyCommands.CREATE, r._virtualId]));
        lines._currentIds.push(...newLines.map((r) => r._virtualId));
        // Un solo onchange del padre: recalcula totales (Rollos / Kg según guía).
        await lines._onUpdate();
        // Deja listo el siguiente lote: cuenta en cero y referencia continuada.
        await record.update({ generate_count: 0, generate_ref_start: refs.next });
    }
}

registry.category("view_widgets").add("generate_roll_lines", { component: GenerateRollLines });
