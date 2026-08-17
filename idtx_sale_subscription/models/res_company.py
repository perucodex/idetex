# -*- coding: utf-8 -*-
from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    # Cómo se describe el periodo en la línea de la factura que genera el
    # cron de suscripciones.
    idtx_subscription_period_format = fields.Selection(
        selection=[
            ('range', 'Rango de fechas (ej. "1 mes 14/08/2026 hasta 13/09/2026")'),
            ('period_month', 'Periodo mensual (ej. "Periodo Agosto 2026")'),
        ],
        string='Formato de periodo en factura de suscripción',
        default='range', required=True,
        help='Formato del texto de periodo que se agrega a la descripción '
             'del producto en la factura generada por las suscripciones.')
