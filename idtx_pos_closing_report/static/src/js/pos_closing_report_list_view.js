/** @odoo-module **/

import { listView } from "@web/views/list/list_view";
import { registry } from "@web/core/registry";

export const idtxPosClosingReportListView = {
    ...listView,
    props: (genericProps, view) => {
        const props = listView.props(genericProps, view);
        props.allowSelectors = false;
        return props;
    },
};

registry.category("views").add("idtx_pos_closing_report_list", idtxPosClosingReportListView);
