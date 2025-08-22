/** @odoo-module */

import { patch } from "@web/core/utils/patch";
import { MrpDisplayAction } from "@mrp_workorder/mrp_display/mrp_display_action";

patch(MrpDisplayAction.prototype, {
    get fieldsStructure() {
        let result = super.fieldsStructure;
        result["mrp.workorder"].push('progress');
        result["mrp.workorder"].push('weaving_wo');
        result["mrp.workorder"].push('weave_type');
        result["mrp.workorder"].push('employee_id');
        result["mrp.workorder"].push('equipment_ids');
        result["mrp.workorder"].push('roll_ids');
        return (result);
    }
});
