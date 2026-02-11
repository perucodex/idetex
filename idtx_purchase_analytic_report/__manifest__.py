# -*- coding: utf-8 -*-
{
    'name': "Purchase Analytic Report",

    'summary': "Reporte de compras por cuenta analítica basado en órdenes de compra",

    'description': """
Reporte tipo Pivot para analizar compras por:
- Cuenta Analítica (Centro de Costo)
- Producto
Basado en purchase.order.line
    """,

    'author': "Codex Development",
    'website': "https://www.perucodex.com",

    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/15.0/odoo/addons/base/data/ir_module_category_data.xml
    # for the full list
    'category': 'Purchase',
    'version': '19.0.0.0',
    'license': 'LGPL-3',

    # any module necessary for this one to work correctly
    'depends': [
        'purchase',
        'analytic',
    ],

    # always loaded
    'data': [
        'security/group_par.xml',
        'security/ir.model.access.csv',
        'views/purchase_analytic_report_views.xml',
        'views/purchase_analytic_report_menu.xml',
    ],
}

