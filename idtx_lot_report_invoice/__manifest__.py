# -*- coding: utf-8 -*-
{
    'name': "Lotes en Factura",

    'summary': "Mostrar lotes en facturas y boletas",

    'description': """
Modulo para mostrar los lotes en los comprobantes de pago, si existen.
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
        'account',
        'point_of_sale',
        'stock_account',
        'idtx_laboratory',
        ],

    # always loaded
    'data': [
        # 'security/ir.model.access.csv',
        'views/report_invoice.xml',
    ],
}

