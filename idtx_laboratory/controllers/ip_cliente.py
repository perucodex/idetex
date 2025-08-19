from odoo import http
from odoo.http import request

class MyController(http.Controller):

    @http.route('/ip_client', type='http', auth='public', methods=['GET'], csrf=False)
    def test(self, **kwargs):
        # Capturar la IP del cliente
        client_ip = request.httprequest.remote_addr
        return f"La IP del cliente es: {client_ip}"
