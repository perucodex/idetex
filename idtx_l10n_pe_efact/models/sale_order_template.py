# -*- coding: utf-8 -*-

from odoo import fields, models

from .account_move import PROCESO_SELECTION


class SaleOrderTemplate(models.Model):
    _inherit = 'sale.order.template'

    # Tipo de servicio por defecto de la plantilla (alquileres): al usar la
    # plantilla en una cotización/suscripción, el pedido lo hereda y de ahí
    # pasa a cada factura (fila PROCESO del formato efact).
    proceso = fields.Selection(PROCESO_SELECTION, string='Proceso')
