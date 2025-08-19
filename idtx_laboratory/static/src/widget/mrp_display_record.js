/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { MrpMenuDialog } from "@mrp_workorder/mrp_display/dialog/mrp_menu_dialog";

patch(MrpMenuDialog.prototype, {
    async readScaleWithClientIP() {
        try {
            // Obtener IP del cliente desde el endpoint
            const ip = await this._getClientIP();
            if (!ip) {
                console.error("No se recibió la IP del cliente");
                return;
            }
            console.log("IP del cliente:", ip);

            // Llamar al método Python pasando la IP
            await this._rpc({
                model: 'mrp.workorder',
                method: 'action_read_scale',
                args: [],
                kwargs: { client_ip: ip },
                record: this.props.record.id,
            });
        } catch (err) {
            console.error("Error al leer balanza con IP del cliente:", err);
        }
    },

    async _getClientIP() {
        try {
            const resp = await fetch('/ip_client');
            if (!resp.ok) throw new Error("No se pudo obtener IP del cliente");
            const text = await resp.text();
            return text.trim();
        } catch (err) {
            console.error("Error obteniendo IP del cliente:", err);
            return null;
        }
    },
});
