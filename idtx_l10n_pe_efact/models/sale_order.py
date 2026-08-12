# -*- coding: utf-8 -*-

from odoo import api, fields, models

from .account_move import PROCESO_SELECTION


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    # Tipo de servicio (alquileres): se define en la suscripción/pedido y
    # cada factura generada (incluidas las recurrentes de la suscripción)
    # lo hereda para imprimirlo en la fila PROCESO del formato efact.
    proceso = fields.Selection(PROCESO_SELECTION, string='Proceso')
    idtx_rental_company = fields.Boolean(related='company_id.idtx_rental_subscriptions')

    def _prepare_invoice(self):
        vals = super()._prepare_invoice()
        if self.proceso:
            vals['proceso'] = self.proceso
        return vals

    # OJO: al sobreescribir un método @api.onchange hay que RE-DECLARAR el
    # decorador — sin él, el override "des-registra" el onchange completo y
    # la plantilla deja de aplicar líneas, plan, notas, todo.
    @api.onchange('sale_order_template_id')
    def _onchange_sale_order_template_id(self):
        res = super()._onchange_sale_order_template_id()
        for order in self:
            if order.sale_order_template_id.proceso:
                order.proceso = order.sale_order_template_id.proceso
        return res
