/** @odoo-module **/

/**
 * Widget de campo "month_year": un selector de Mes/Año.
 *
 * Reutiliza el campo `date` estándar de Odoo 19 (DateTimeField), que ya soporta
 * `min_precision` / `max_precision` en el datetime picker. Con
 * `min_precision='months'`, al hacer clic en un mes el picker fija el día 1 de
 * ese mes (ver `zoomOrSelect` en core/datetime/datetime_picker.js: si ya está en
 * el nivel mínimo, selecciona `range[0]` = inicio del mes).
 *
 * Añade dos cosas sobre el campo date:
 *   1) FORMATO de visualización `MM/yyyy` (p. ej. "06/2026"), tanto en el botón
 *      de display como en solo-lectura  -> getFormattedValue().
 *   2) El input editable y el PARSEO al teclear también usan `MM/yyyy`, pasando
 *      `format` al picker -> setup() (copia del core con esa única diferencia).
 *      parseDate("06/2026", {format:"MM/yyyy"}) devuelve el día 1 del mes.
 *
 * Uso en la vista:
 *     <field name="period" widget="month_year"/>
 * Opcional (override de precisión):
 *     <field name="period" widget="month_year"
 *            options="{'min_precision': 'months', 'max_precision': 'years'}"/>
 */

import { onWillRender, useEffect, useRef, useState } from "@odoo/owl";
import { useDateTimePicker } from "@web/core/datetime/datetime_picker_hook";
import { areDatesEqual } from "@web/core/l10n/dates";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { DateTimeField, dateField } from "@web/views/fields/datetime/datetime_field";

const { DateTime } = luxon;

export class MonthYearField extends DateTimeField {
    /** Formato de mes/año usado para mostrar Y para parsear el input. */
    get monthYearFormat() {
        return "MM/yyyy";
    }

    /**
     * Muestra solo mes/año (sin día). Se usa en solo-lectura y en el botón de
     * edición (cuando el campo tiene valor y no está enfocado).
     * @override
     */
    getFormattedValue(valueIndex) {
        const value = this.values[valueIndex];
        return value ? value.toFormat(this.monthYearFormat) : "";
    }

    /**
     * Copia de DateTimeField.setup() (Odoo 19) con UNA sola diferencia: se pasa
     * `format: this.monthYearFormat` al picker, de modo que el servicio formatee
     * el input editable y parsee el texto tecleado como MM/yyyy (en vez de la
     * fecha completa del locale). El resto es idéntico al core.
     * @override
     */
    setup() {
        const getPickerProps = () => {
            const value = this.getRecordValue();
            const pickerProps = {
                value,
                type: this.field.type,
                range: this.isRange(value),
                showRangeToggler:
                    this.relatedField && !this.props.required && !this.props.alwaysRange,
                onToggleRange,
            };
            if (this.props.maxDate) {
                pickerProps.maxDate = this.parseLimitDate(this.props.maxDate);
            }
            if (this.props.minDate) {
                pickerProps.minDate = this.parseLimitDate(this.props.minDate);
            }
            if (!isNaN(this.props.rounding)) {
                pickerProps.rounding = this.props.rounding;
            } else if (this.props.showSeconds) {
                pickerProps.rounding = 0;
            }
            if (this.props.maxPrecision) {
                pickerProps.maxPrecision = this.props.maxPrecision;
            }
            if (this.props.minPrecision) {
                pickerProps.minPrecision = this.props.minPrecision;
            }
            return pickerProps;
        };

        const onToggleRange = () => {
            this.state.range = !this.state.range;
            if (this.state.range) {
                let values = this.values;
                const optionalFieldIndex = values[0] ? 1 : 0;
                if (!values[0] && !values[1]) {
                    values = [DateTime.local(), DateTime.local()];
                }
                values[optionalFieldIndex] = optionalFieldIndex
                    ? values[0].plus({ hours: 1 })
                    : values[1].minus({ hours: 1 });
                this.state.focusedDateIndex = 0;
                this.state.value = values;
            } else {
                const mainFieldIndex = this.props.name === this.startDateField ? 0 : 1;
                this.state.focusedDateIndex = mainFieldIndex;
                this.state.value[mainFieldIndex ? 0 : 1] = false;
            }
        };

        const dateTimePicker = useDateTimePicker({
            target: "root",
            showSeconds: this.props.showSeconds,
            format: this.monthYearFormat, // <-- ÚNICA diferencia con el core
            get pickerProps() {
                return getPickerProps();
            },
            onChange: () => {
                this.state.range = this.isRange(this.state.value);
            },
            onClose: () => {
                this.picker.activeInput = "";
            },
            onApply: async () => {
                const toUpdate = {};
                if (Array.isArray(this.state.value)) {
                    [toUpdate[this.startDateField], toUpdate[this.endDateField]] = this.state.value;
                } else {
                    toUpdate[this.props.name] = this.state.value;
                }
                // Si startDateField o endDateField no están definidos, descarta
                // los campos sin cambios.
                for (const fieldName in toUpdate) {
                    if (areDatesEqual(toUpdate[fieldName], this.props.record.data[fieldName])) {
                        delete toUpdate[fieldName];
                    }
                }
                if (Object.keys(toUpdate).length) {
                    await this.props.record.update(toUpdate);
                }
            },
        });
        // Suscribe a los cambios del estado del picker.
        this.state = useState(dateTimePicker.state);
        this.picker = useState({ activeInput: "" });
        this.openPicker = dateTimePicker.open;

        this.startDate = useRef("start-date");
        this.endDate = useRef("end-date");

        useEffect(
            () => {
                [this.startDate, this.endDate].forEach((ref, index) => {
                    if (ref.el?.getAttribute("data-field") === this.picker.activeInput) {
                        ref.el.focus();
                        this.openPicker(index);
                    }
                });
            },
            () => [this.startDate.el?.tagName, this.endDate.el?.tagName, this.picker.activeInput]
        );

        onWillRender(() => this.triggerIsDirty());

        this.futureWarningMsg = _t("This date is in the future");
    }
}

export const monthYearField = {
    ...dateField,
    component: MonthYearField,
    displayName: _t("Mes / Año"),
    supportedTypes: ["date"],
    extractProps(fieldInfo, dynamicInfo) {
        const props = dateField.extractProps(fieldInfo, dynamicInfo);
        // Por defecto el picker baja solo hasta "meses": un clic en el mes
        // selecciona el día 1. Se puede sobreescribir con options.
        props.minPrecision = fieldInfo.options.min_precision || "months";
        props.maxPrecision = fieldInfo.options.max_precision || "decades";
        return props;
    },
};

registry.category("fields").add("month_year", monthYearField);
