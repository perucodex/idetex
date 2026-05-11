# -*- coding: utf-8 -*-
{
    'name': 'POS Terminos de Pago',
    'summary': 'Selecciona termino de pago en el POS al usar metodos marcados',
    'description': """
Permite marcar metodos de pago del POS con "Usa Terminos de Pago".
Al elegir uno de esos metodos, el cajero debe seleccionar un termino de pago
en una pantalla emergente; ese termino se aplica a la factura generada y la
orden se marca automaticamente para facturar.
    """,
    'author': 'Codex Development',
    'website': 'https://www.perucodex.com',
    'category': 'Point of Sale',
    'version': '19.0.0.0',
    'license': 'LGPL-3',
    'depends': ['point_of_sale', 'account'],
    'data': [
        'views/pos_payment_method_views.xml',
    ],
    'assets': {
        'point_of_sale._assets_pos': [
            'idtx_pos_payment_term/static/src/**/*',
        ],
    },
    'installable': True,
    'application': False,
}
