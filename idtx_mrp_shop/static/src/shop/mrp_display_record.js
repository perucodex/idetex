/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { MrpDisplayRecord } from "@mrp_workorder/mrp_display/mrp_display_record";
import { Many2OneField } from "@web/views/fields/many2one/many2one_field";

patch(MrpDisplayRecord.components, {
    Many2OneField,
});
