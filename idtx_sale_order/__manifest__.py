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
    'sequence': 0,

    # any module necessary for this one to work correctly
    'depends': [
            'base',
            'sale_management',
            'sale_stock',
            'sale_subscription',
            'idtx_product_development',
            'idtx_laboratory',
            'idtx_printing',
        ],

    # always loaded
    'data': [
        'data/product.color.csv',
        'security/ir.model.access.csv',
        'report/ir_actions_report_templates.xml',
        'report/ir_actions_report.xml',
        'report/report_technical_sheet_customer.xml',
        'views/account_incoterms_views.xml',
        'views/account_payment_term_views.xml',
        'views/lab_dev_views.xml',
        'views/mrp_production_views.xml',
        'views/mrp_routing_views.xml',
        'views/portal_price_items_template.xml',
        # 'views/product_code_system_views.xml',
        'views/product_color_views.xml',
        'views/res_config_settings_views.xml',
        'views/sale_order_portal_templates.xml',
        'views/sale_order_views.xml',
        'views/sale_quotation_views.xml',
        'wizards/size_qty_wizard_views.xml',
    ],
    
    'assets': {
        'web.assets_backend': [
            'idtx_sale_order/static/src/price_items/**/*',
        ],
        'web.report_assets_pdf': [
            'idtx_sale_order/static/src/css/ir_actions_report_templates.css',
        ],
        'web.report_assets_common': [
            'idtx_sale_order/static/src/css/ir_actions_report_templates.css',
        ],
    },
}

