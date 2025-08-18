// /** @odoo-module **/
// import { patch } from "@web/core/utils/patch";
// import { MrpDisplayRecord } from "@mrp_workorder/mrp_display/mrp_display_record";

// patch(MrpDisplayRecord.prototype, {
//     get progressValue() {
//         return this.props.record.data.progress || 0;
//     },
// });

/** @odoo-module **/

import { MrpDisplayRecord } from "@mrp/components/mrp_display_record/mrp_display_record";

/**
 * Extensión de MrpDisplayRecord para agregar el getter progress
 */
export class MrpDisplayRecordProgress extends MrpDisplayRecord {
    /**
     * Retorna el progreso de la orden de trabajo.
     * Intenta primero record.progress, si no existe usa record.data.progress, si no 0
     */
    get progress() {
        return this.record?.progress || this.record?.data?.progress || 0;
    }
}

// Sobrescribir el componente original para usar esta extensión
MrpDisplayRecord.components = {
    ...MrpDisplayRecord.components,
};
