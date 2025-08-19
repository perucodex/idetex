/** @odoo-module */

import { patch } from "@web/core/utils/patch";
import { MrpDisplayRecord } from "@mrp_workorder/mrp_display/mrp_display_record";

patch(MrpDisplayRecord.prototype, {

    async validate() {
        console.log("Entró");
        return super.validate();
    },    

    async callAction(actionName) {
        if (actionName !== "action_read_scale") {
            console.log("No entró");
            return this._super(...arguments);
        }
        try {
            console.log("Entró");
            // 1) Obtener IP interna desde el navegador (puede ser null si el navegador la oculta)
            const internalIP = await getFirstPrivateIP(1500);

            // 2) Llamar a tu método Python y pasar IP en el contexto
            //    (evitamos romper la firma del método con args posicionales)
            const res = await this.orm.call(
                "mrp.workorder",
                "action_read_scale",
                [this.props.record.resId],
                { context: { client_internal_ip: internalIP } }
            );

            // 3) Notificación visual
            const msgIP = internalIP || "no disponible (mDNS oculto)";
            this.notification.add(
                `Lectura de balanza OK. IP cliente: ${msgIP}`,
                { type: "success" }
            );

            return res;
        } catch (error) {
            this.notification.add(
                `Error al consultar balanza: ${error?.message || error}`,
                { type: "danger" }
            );
        }
    },
});
