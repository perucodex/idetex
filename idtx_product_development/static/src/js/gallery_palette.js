/** @odoo-module **/

import { Component, useState, onWillStart } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

export class GalleryPalette extends Component {
    static template = "fabric_gallery.GalleryPalette";

    setup() {
        this.orm = useService("orm");
        this.state = useState({ images: [] });

        onWillStart(async () => {
            const records = await this.orm.searchRead("fabric.image.palette", [], ["id", "name", "image"]);
            this.state.images = records;
        });
    }
}

registry.category("fields").add("gallery_palette", {
    component: GalleryPalette,
});
