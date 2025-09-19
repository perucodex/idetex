from odoo.addons.sale.controllers.portal import CustomerPortal
from odoo import http
from odoo.http import request

class CustomerPortalCustom(CustomerPortal):

    @http.route(['/my/orders/<int:order_id>/price_items'],
                type='http', auth="public", website=True, sitemap=False)
    def portal_order_price_items(self, order_id, access_token=None, **kw):
        # reaprovechamos toda la seguridad ya existente
        order_sudo = self._document_check_access('sale.order', order_id, access_token=access_token)
        backend_url = f'/odoo/action-{order_sudo._get_portal_return_action().id}/{order_sudo.id}'
        return request.render(
            'idtx_laboratory.sale_price_items_preview',
            {
                'order': order_sudo, 
                'access_token': access_token,
                'backend_url': backend_url,
            }
        )