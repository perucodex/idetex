/** @odoo-module **/

import { Component, useState, onMounted, onWillUnmount } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

export class ImpresoraDashboard extends Component {
    static template = "idtx_laboratory.ImpresoraDashboard";

    // Declaramos todos los props que Odoo le va a pasar al componente como campo
    static props = {
        readonly: { type: Boolean, optional: true },
        id: { type: [Number, String], optional: true },
        name: { type: String, optional: true },
        record: { type: Object, optional: true },
    };

    setup() {
        this.http = useService("http");
        this.state = useState({
            data: {},
            error: null,
        });
        this._interval = null;

        const fetchData = async () => {
            try {
                const resId = this.props.record?.resId;
                const stateVal = this.props.record?.data?.state;
                
                // Solo llamamos al backend si está conectado
                if (!resId || stateVal !== "con") {
                    return;
                }

                const url = `/impresora/data/${resId}`;
                const json = await this.http.get(url);
                this.state.data = json || {};
                this.state.error = null;
            } catch (e) {
                this.state.error = "No se pudo obtener datos de la impresora.";
            }
        };

        onMounted(async () => {
            await fetchData();
            this._interval = setInterval(fetchData, 1000);
        });

        onWillUnmount(() => {
            if (this._interval) clearInterval(this._interval);
        });
    }
}

// Widget para usar en un campo de formulario
const fieldRegistry = registry.category("fields");
fieldRegistry.add("impresora_dashboard", {
    component: ImpresoraDashboard,
});
