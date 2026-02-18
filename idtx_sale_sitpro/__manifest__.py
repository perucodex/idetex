# -*- coding: utf-8 -*-
{
    'name': "Sitpro",

    'summary': "Integración con SITPRO",

    'description': """
Integración con software sitpro para ingresar registro de ordenes desde Odoo
e insertar el registro en tabla fox (dbf)
    """,

    'author': "Codex Development",
    'website': "https://www.perucodex.com",

    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/15.0/odoo/addons/base/data/ir_module_category_data.xml
    # for the full list
    'category': 'Sale',
    'version': '19.0.0.0',
    'license': 'LGPL-3',

    # any module necessary for this one to work correctly
    'depends': ['base','idtx_sale_order'],

    # always loaded
    'data': [
        'security/ir.model.access.csv',
        'views/account_payment_term_views.xml',
        'views/res_users_views.xml',
        'views/sale_order_views.xml',
        'views/sitpro_sale_type_views.xml',
        # 'views/templates.xml',
    ],
}

