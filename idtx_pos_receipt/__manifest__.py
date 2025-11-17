# -*- coding: utf-8 -*-
{
    'name': "Recibo",

    'summary': "Recibo sin info",

    'description': """
No imprime información de la empresa cuando no tiene comprobante de pago.
    """,

    'author': "Codex Development",
    'website': "https://www.perucodex.com",

    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/15.0/odoo/addons/base/data/ir_module_category_data.xml
    # for the full list
    'category': 'Uncategorized',
    'version': '0.1',
    'license': 'LGPL-3',

    # any module necessary for this one to work correctly
    'depends': [
        'base',
        'point_of_sale',
        'idtx_sale_order',
        ],

    # always loaded
    'data': [
        # 'security/ir.model.access.csv',
        # 'views/views.xml',
        # 'views/templates.xml',
    ],
    'assets': {
        'point_of_sale._assets_pos': [
            'idtx_pos_receipt/static/src/**/*',
        ],
    },
}

