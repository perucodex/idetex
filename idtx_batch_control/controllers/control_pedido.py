# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request

class KioskControlPedido(http.Controller):

    @http.route('/kiosk/control_pedido', type='http', auth='public')
    def kiosk_page(self, **kw):
        return request.render('idtx_batch_control.kiosk_control_pedido_page', {})

    @http.route('/kiosk/control_pedido/data', type='http', auth='public', csrf=False)
    def kiosk_data(self, limit=300, **kw):
        try:
            limit = int(limit or 300)
        except Exception:
            limit = 300

        domain = [('state', 'in', ('on', 'de'))]
        order = 'num_days desc, state desc, fecoc desc, numordped desc'

        fields = ['fecoc', 'numordped', 'num_days', 'state', 'area']

        records = request.env['control.pedido'].sudo().search_read(
            domain, fields=fields, order=order, limit=limit
        )

        return request.make_json_response({
            'count': len(records),
            'limit': limit,
            'records': records,
        })
