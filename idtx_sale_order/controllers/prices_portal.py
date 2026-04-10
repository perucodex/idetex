from odoo.addons.sale.controllers.portal import CustomerPortal
from odoo import http
from odoo.http import request
import json

class CustomerPortalCustom(CustomerPortal):

    def _prepare_line_price_items(self, order_sudo):
        normalized = {}
        for line in order_sudo.order_line:
            entries = []
            try:
                raw_items = json.loads(line.price_items or '{}')
            except (TypeError, ValueError):
                raw_items = {}

            if isinstance(raw_items, dict):
                for key, value in raw_items.items():
                    if str(key).startswith('__'):
                        continue
                    if isinstance(value, dict):
                        label = value.get('label') or key
                        price = value.get('price', 0.0)
                    else:
                        label = key
                        price = value
                    try:
                        price = float(price or 0.0)
                    except (TypeError, ValueError):
                        price = 0.0
                    entries.append({'label': label, 'price': price})

            normalized[line.id] = entries
        return normalized

    @http.route(['/my/orders/<int:order_id>/price_items'], type='http', auth="public", website=True, sitemap=False)
    def portal_order_price_items(self, order_id, access_token=None, **kw):
        # reaprovechamos toda la seguridad ya existente
        order_sudo = self._document_check_access('sale.order', order_id, access_token=access_token)
        backend_url = f'/odoo/action-{order_sudo._get_portal_return_action().id}/{order_sudo.id}'
        values = {
            'sale_order': order_sudo,
            'line_price_items': self._prepare_line_price_items(order_sudo),
            'product_documents': order_sudo._get_product_documents(),
            'message': '',
            'report_type': 'html',
            'backend_url': backend_url,
            'res_company': order_sudo.company_id, 
            'page_name': 'quote',
        }
        history_session_key = 'my_orders_history'
        values = self._get_page_view_values(order_sudo, access_token, values, history_session_key, False)
        return request.render(
            'idtx_sale_order.sale_price_items_preview', values
        )