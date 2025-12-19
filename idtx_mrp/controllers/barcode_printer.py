from odoo import http
from odoo.http import request
from odoo.exceptions import UserError
import ipaddress

class ZPLPrintController(http.Controller):

    @http.route('/zpl/print', type='jsonrpc', auth='user')
    def print_zpl(self, record_id=None, printer_ip=None):

        if not record_id:
            raise UserError("No se recibió record_id") 
        self.children_classes.get(record_id)

        if not printer_ip:
            raise UserError("No se recibió la IP de la impresora")

        try:
            ipaddress.ip_address(printer_ip)
        except ValueError:
            raise UserError("IP de impresora inválida")

        roll = request.env['mrp.workorder.roll'].sudo().browse(int(record_id))
        if not roll.exists():
            raise UserError("Registro no encontrado")

        zpl = roll.create_zpl()
        roll._print_zpl_to_network(zpl, printer_ip)

        return {"ok": True}
