/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { MrpDisplayRecord } from "@mrp_workorder/mrp_display/mrp_display_record";

patch(MrpDisplayRecord.prototype, {

    async readScaleWithClientIP() {
        try {
            const ip = await this.getLocalIP();
            console.log("IP interna del cliente:", ip);

            // Llamamos a la función Python pasando la IP
            await this._rpc({
                model: 'mrp.workorder',
                method: 'action_read_scale',
                args: [[this.props.record.id], ip],  // pasamos la IP como argumento
            });

        } catch (e) {
            console.error("Error obteniendo IP interna:", e);
        }
    },

    getLocalIP() {
        return new Promise((resolve, reject) => {
            const pc = new RTCPeerConnection({iceServers: []});
            pc.createDataChannel(""); // Necesario para Firefox
            pc.createOffer().then(offer => pc.setLocalDescription(offer));
            pc.onicecandidate = (event) => {
                if (!event.candidate) return;
                const ipMatch = /([0-9]{1,3}(\.[0-9]{1,3}){3})/.exec(event.candidate.candidate);
                if (ipMatch) {
                    resolve(ipMatch[1]);
                    pc.close();
                }
            };
        });
    }

});
