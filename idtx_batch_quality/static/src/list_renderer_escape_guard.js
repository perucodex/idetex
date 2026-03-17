/** @odoo-module **/

import { ListRenderer } from "@web/views/list/list_renderer";

const originalOnCellKeydownEditMode = ListRenderer.prototype.onCellKeydownEditMode;

if (typeof originalOnCellKeydownEditMode === "function") {
    ListRenderer.prototype.onCellKeydownEditMode = function (...args) {
        // Guard against Odoo edge case: Esc can be fired with no active editable row.
        if (!this.activeRow) {
            return;
        }
        return originalOnCellKeydownEditMode.apply(this, args);
    };
}
