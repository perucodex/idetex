# -*- coding: utf-8 -*-

from odoo import api, fields, models

PROCESO_SELECTION = [
    ('luz', 'SERVICIO DE CONSUMO DE LUZ'),
    ('agua', 'SERVICIO DE CONSUMO DE AGUA'),
    ('arrendamiento', 'SERVICIO DE ARRENDAMIENTO'),
]


class AccountMove(models.Model):
    _inherit = 'account.move'

    idtx_oc_ref = fields.Char(string='N° O. Compra')
    # Tipo de servicio del comprobante (alquileres): se hereda de la
    # suscripción/pedido al facturar y se imprime en la fila PROCESO del
    # formato efact.
    proceso = fields.Selection(
        PROCESO_SELECTION, string='Proceso', copy=False)

    @api.depends('state', 'move_type')
    def _compute_display_send_button(self):
        super()._compute_display_send_button()
        for move in self:
            if move.is_sale_document() and move.state in ('posted', 'cancel'):
                move.display_send_button = True
