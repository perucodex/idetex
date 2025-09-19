# -*- coding: utf-8 -*-
{
    'name': "Desarrollo de Producto Textil",

    'summary': "Modulo de desarrollo de producto textil",

    'description': """
Gestión de desarrollo de producto textil desde el análisis hasta la creación del estandar
y ficha técnica
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
            'idtx_mrp',
        ],

    # always loaded
    'data': [
        'data/configurate.svg.example.csv',
        'data/product.category.csv',
        'data/intial_company_categories.xml',
        'data/ir_sequence.xml',
        'data/product.appearance.csv',
        'data/product.family.csv',
        'data/product.fiber.csv',
        'data/product.gauge.csv',
        'data/product.title.csv',
        'security/group_dev.xml',
        'security/ir.model.access.csv',
        'report/report_product_analysis.xml',
        'report/report_technical_sheet.xml',
        'report/ir_actions_report.xml',
        'views/configurate_svg_example.xml',
        'views/mrp_routing_views.xml',
        'views/mrp_workorder_batch_views.xml',
        'views/mrp_workorder_roll_views.xml',
        'views/mrp_workorder_views.xml',
        'views/product_analysis_views.xml',
        'views/product_code_system_views.xml',
        'views/product_template_views.xml',
        'views/res_config_settings_views.xml',
        'views/technical_sheet_views.xml',
        'views/dev_menu.xml',
    ],
    
    'assets': {
        'web.assets_backend': [
            'idtx_product_development/static/src/ligament_widget/**/*',
        ],
    },

}

