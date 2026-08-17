# -*- coding: utf-8 -*-
from odoo import _, models
from odoo.tools import format_date


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    def _prepare_invoice_line(self, **optional_values):
        res = super()._prepare_invoice_line(**optional_values)
        order = self.order_id
        company = (order.company_id or self.env.company).sudo()
        if company.idtx_subscription_period_format != 'period_month':
            return res

        # Reproduce EXACTAMENTE la condición de sale_subscription que anexa
        # a la descripción "\n{duration} {inicio} hasta {fin}", para poder
        # quitar ese sufijo y reemplazarlo por "Periodo <Mes> <Año>".
        if self.display_type or self.product_id.type == 'combo':
            return res
        if not (order.plan_id and (self.recurring_invoice
                                   or order.subscription_state == '7_upsell')):
            return res
        if not (self.recurring_invoice and not self._is_delivery()):
            return res

        lang_code = order.partner_id.lang
        new_period_start = self._get_invoice_line_parameters()[0]
        format_start = format_date(self.env, new_period_start, lang_code=lang_code)

        # sale_subscription anexa SIEMPRE como última línea
        # "\n{duración} {inicio} hasta {fin}". Se quita esa última línea (en
        # vez de reconstruir el texto traducido "hasta", que no está en el
        # catálogo de este módulo) validando que contenga la fecha de inicio
        # del periodo — así no se corta por error una descripción multilínea.
        name = res.get('name') or ''
        head, sep, last = name.rpartition('\n')
        if not sep or format_start not in last:
            return res
        base = head

        # "Periodo Agosto 2026" (mes del inicio del periodo, en el idioma del
        # cliente; se capitaliza porque babel devuelve el mes en minúscula).
        month_year = format_date(self.env, new_period_start,
                                 lang_code=lang_code, date_format='LLLL y')
        month_year = month_year[:1].upper() + month_year[1:]
        res['name'] = "%s\n%s" % (base, _("PERIODO %s", month_year.upper()))
        return res
