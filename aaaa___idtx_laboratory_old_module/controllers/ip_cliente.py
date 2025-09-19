# controllers/ip_controller.py
from odoo import http
from odoo.http import request

class MyController(http.Controller):

    @http.route('/ip_client', type='http', auth='public', methods=['GET'], csrf=False)
    def get_ip(self, **kwargs):
        # Apache ya pone la IP real en REMOTE_ADDR
        client_ip = request.httprequest.environ.get('REMOTE_ADDR')
        headers = dict(request.httprequest.headers)
        remote_addr = request.httprequest.environ.get('REMOTE_ADDR')
        xff = request.httprequest.headers.get('X-Forwarded-For')
        return f"REMOTE_ADDR={remote_addr} | X-Forwarded-For={xff} | headers={headers}"
        # if not client_ip:
        #     return "No se recibió la IP del cliente"
        # return f"La IP del cliente es: {client_ip}"
