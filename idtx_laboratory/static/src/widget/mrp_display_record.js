/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { MrpMenuDialog } from "@mrp_workorder/mrp_display/dialog/mrp_menu_dialog";
import { rpc } from "@web/core/network/rpc";

/**
 * Función para obtener la IP local del cliente usando WebRTC
 */
async function getLocalIP() {
    return new Promise((resolve, reject) => {
        const pc = new RTCPeerConnection({ iceServers: [] });
        pc.createDataChannel("");
        pc.createOffer().then(offer => pc.setLocalDescription(offer));
        pc.onicecandidate = (event) => {
            if (!event.candidate) return;
            const ipRegex = /([0-9]{1,3}(\.[0-9]{1,3}){3})/;
            const ipMatch = ipRegex.exec(event.candidate.candidate);
            if (ipMatch) {
                resolve(ipMatch[1]);
                pc.close();
            }
        };
        // Timeout por si no se obtiene la IP
        setTimeout(() => reject("No se pudo obtener la IP local"), 10000);
    });
}

patch(MrpMenuDialog.prototype, {
    async readScaleWithClientIP(workorderId) {
        try {
            const clientIP = await getLocalIP();
            console.log("IP del cliente:", clientIP);

            const result = await rpc.query({
                model: "mrp.workorder",
                method: "action_read_scale",
                args: [[workorderId], clientIP],  // Pasamos la IP al método Python
            });

            console.log("Resultado de action_read_scale:", result);

        } catch (error) {
            console.error("Error al leer balanza con IP del cliente:", error);
        }
    },
});
