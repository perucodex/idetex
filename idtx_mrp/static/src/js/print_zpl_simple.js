/** @odoo-module **/

import { registry } from "@web/core/registry";
import { rpc } from "@web/core/network/rpc";

async function printZPLWithIP(env, action) {
    const recordIds = action.params.record_ids;

    // 1️⃣ Buscar IP guardada
    let printerIp = localStorage.getItem("zpl_printer_ip");

    // 2️⃣ Si no existe → pedirla
    if (!printerIp) {
        printerIp = prompt("Ingresá la IP de la impresora Zebra:");
        if (!printerIp) {
            alert("Impresión cancelada");
            return;
        }
        localStorage.setItem("zpl_printer_ip", printerIp);
    }

    await rpc("/web/dataset/call_kw", {
        model: "mrp.workorder.roll",
        method: "print_zpl_with_ip",
        args: [recordIds, printerIp],
        kwargs: {},
    });
}

registry.category("actions").add("print_zpl_ip", printZPLWithIP);
