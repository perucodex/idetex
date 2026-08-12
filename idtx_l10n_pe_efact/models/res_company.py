# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models

class ResCompany(models.Model):
    _inherit = 'res.company'

    l10n_pe_edi_provider = fields.Selection(
        selection_add=[
            ('efact', 'Efact'),
        ],
    )
    # Habilita en la empresa los campos N° O. Compra y Proceso (facturas,
    # pedidos/suscripciones y plantillas). DESACTIVADO por defecto: el
    # usuario lo marca en las empresas de alquiler.
    idtx_rental_subscriptions = fields.Boolean(
        'Alquiler / suscripciones',
        help='Muestra en las facturas de esta empresa los campos '
             'N° O. Compra y Proceso (tipo de servicio).')