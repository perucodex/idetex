# -*- coding: utf-8 -*-
{
    'name': "Ventas Textil",

    'summary': "Modulo de ventas Textiles",

    'description': """
Gestiona la carga de precios y productos en tus cotizaciones
    """,

    'author': "Codex Development",
    'website': "https://www.perucodex.com",

    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/15.0/odoo/addons/base/data/ir_module_category_data.xml
    # for the full list
    'category': 'Producción Textil',
    'version': '0.1',
    'license': 'LGPL-3',

    # any module necessary for this one to work correctly
    'depends': [
            'base',
            'sale_management',
            'sale_stock',
            'idtx_product_development',
            'idtx_laboratory',
        ],

    # always loaded
    'data': [
        'data/product.color.csv',
        'security/ir.model.access.csv',
        'report/ir_actions_report_templates.xml',
        'views/account_incoterms_views.xml',
        'views/account_payment_term_views.xml',
        'views/mrp_production_views.xml',
        'views/mrp_routing_views.xml',
        'views/portal_price_items_template.xml',
        'views/product_color_views.xml',
        'views/res_company_views.xml',
        'views/sale_order_views.xml',
        'views/sale_quotation_views.xml',
    ],
    
    'assets': {
        'web.assets_backend': [
            'idtx_sale_order/static/src/price_items/**/*',
        ],
    },

}

