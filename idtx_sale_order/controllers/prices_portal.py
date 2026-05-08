from odoo.addons.sale.controllers.portal import CustomerPortal
from odoo import http, _
from odoo.http import request
from odoo.addons.portal.controllers.portal import pager as portal_pager
from odoo.exceptions import UserError
import json

class CustomerPortalCustom(CustomerPortal):

    @http.route(['/my/counters'], type='jsonrpc', auth="user", website=True, readonly=True)
    def counters(self, counters, **kw):
        res = super().counters(counters, **kw)
        partner = request.env.user.partner_id
        SaleOrder = request.env['sale.order']

        if SaleOrder.has_access('read'):
            if 'quotation_count' in counters:
                res['quotation_count'] = SaleOrder.search_count(self._prepare_quotations_domain(partner))
            if 'quotation_signed_count' in counters:
                res['quotation_signed_count'] = SaleOrder.search_count(
                    self._prepare_signed_quotations_domain(partner)
                )
        else:
            if 'quotation_count' in counters:
                res['quotation_count'] = 0
            if 'quotation_signed_count' in counters:
                res['quotation_signed_count'] = 0

        return res

    def _prepare_home_portal_values(self, counters):
        values = super()._prepare_home_portal_values(counters)
        partner = request.env.user.partner_id
        SaleOrder = request.env['sale.order']

        if 'quotation_count' in counters:
            values['quotation_count'] = (
                SaleOrder.search_count(self._prepare_quotations_domain(partner))
                if SaleOrder.has_access('read') else 0
            )

        if 'quotation_signed_count' in counters:
            values['quotation_signed_count'] = (
                SaleOrder.search_count(self._prepare_signed_quotations_domain(partner))
                if SaleOrder.has_access('read') else 0
            )

        return values

    def _prepare_quotations_domain(self, partner):
        return [
            ('partner_id', 'child_of', [partner.commercial_partner_id.id]),
            ('state', '=', 'sent'),
            ('is_quote', '=', True),
            ('signed_on', '=', False),
        ]

    def _prepare_signed_quotations_domain(self, partner):
        return [
            ('partner_id', 'child_of', [partner.commercial_partner_id.id]),
            ('state', '=', 'sent'),
            ('is_quote', '=', True),
            ('signed_on', '!=', False),
        ]

    def _prepare_orders_domain(self, partner):
        return [
            ('partner_id', 'child_of', [partner.commercial_partner_id.id]),
            ('is_quote', '=', False),
            ('state', 'in', ('sale', 'sent','pending_admin_approval','pending_final_approval')),
        ]
    
    def _prepare_signed_quotation_portal_rendering_values(
        self, page=1, date_begin=None, date_end=None, sortby=None, **kwargs
    ):
        SaleOrder = request.env['sale.order']

        if not sortby:
            sortby = 'date'

        partner = request.env.user.partner_id
        values = self._prepare_portal_layout_values()
        url = "/my/signed_quotes"
        domain = self._prepare_signed_quotations_domain(partner)
        searchbar_sortings = self._get_sale_searchbar_sortings()
        sort_order = searchbar_sortings[sortby]['order']

        if date_begin and date_end:
            domain += [('create_date', '>', date_begin), ('create_date', '<=', date_end)]

        url_args = {'date_begin': date_begin, 'date_end': date_end}

        if len(searchbar_sortings) > 1:
            url_args['sortby'] = sortby

        pager_values = portal_pager(
            url=url,
            total=SaleOrder.search_count(domain) if SaleOrder.has_access('read') else 0,
            page=page,
            step=self._items_per_page,
            url_args=url_args,
        )
        orders = (
            SaleOrder.search(domain, order=sort_order, limit=self._items_per_page, offset=pager_values['offset'])
            if SaleOrder.has_access('read') else SaleOrder
        )

        values.update({
            'date': date_begin,
            'quotations': orders.sudo(),
            'orders': SaleOrder,
            'page_name': 'signed_quote',
            'pager': pager_values,
            'default_url': url,
        })

        if len(searchbar_sortings) > 1:
            values.update({
                'sortby': sortby,
                'searchbar_sortings': searchbar_sortings,
            })

        return values

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

    @http.route(['/my/orders/<int:order_id>/accept'], type='jsonrpc', auth="public", website=True)
    def portal_quote_accept(self, order_id, access_token=None, name=None, signature=None):
        try:
            return super().portal_quote_accept(
                order_id, access_token=access_token, name=name, signature=signature
            )
        except UserError as e:
            request.env.cr.rollback()
            return {'error': str(e)}

    @http.route(['/my/signed_quotes', '/my/signed_quotes/page/<int:page>'], type='http', auth="user", website=True)
    def portal_my_signed_quotes(self, **kwargs):
        values = self._prepare_signed_quotation_portal_rendering_values(**kwargs)
        request.session['my_quotations_history'] = values['quotations'].ids[:100]
        return request.render("sale.portal_my_quotations", values)
