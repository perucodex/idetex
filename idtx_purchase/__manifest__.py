# -*- coding: utf-8 -*-
{
    'name': "Compras",

    'summary': "Modificación de reporte",

    'description': """
Muestra fechas de orden y de aprobación en reporte y vista
    """,

    'author': "Codex Development",
    'website': "https://www.perucodex.com",

    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/15.0/odoo/addons/base/data/ir_module_category_data.xml
    # for the full list
    'category': 'Uncategorized',
    'version': '0.1',
    'license': 'LGPL-3',
    'sequence': 0,

    # any module necessary for this one to work correctly
    'depends': ['base','purchase','web'],

    # always loaded
    'data': [
        'data/product_data.xml',
        'security/ir.model.access.csv',
        # 'security/payment_term_access.xml',
        'data/report_layout.xml',
        'report/purchase_order_templates.xml',
        'report/report_templates.xml',
        'views/purchase_views.xml',
    ],
    'assets': {
        'web.report_assets_common': [
            'idtx_purchase/static/src/scss/layout_boxed_purchase.scss',
        ],
    }
}

