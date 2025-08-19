from odoo import http

class IpClient(http.Controller):
    @http.route('/get_ip', type='http', auth='public')
    def get_ip(self, **kw):
        request = http.request
        ip = request.httprequest.headers.get('X-Forwarded-For')
        if not ip:
            ip = request.httprequest.headers.get('X-Real-IP')
        if not ip:
            ip = request.httprequest.remote_addr  # fallback
        return f"IP del cliente: {ip}"
