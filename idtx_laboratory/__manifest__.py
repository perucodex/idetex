# -*- coding: utf-8 -*-
{
    'name': "Laboratory & Product Development",

    'summary': "Laboratory and Product Development modulo created for IDETEX",

    'description': """
Laboratory & Product Development module allows for the creation of products, bills of materials, 
colors, technical sheets, coding, and customer quotes based on fibers, inputs, and production routes.
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
    'depends': ['base',
                'product',
                'sale',
                ],

    # always loaded
    'data': [
        'security/group_lab.xml',
        'security/ir.model.access.csv',
        'data/color.fiber.csv',
        'data/color.intensity.csv',
        'data/color.process.type.csv',
        'data/color.range.csv',
        'data/ir_sequence.xml',
        'data/product.appearance.csv',
        'data/product.color.csv',
        'data/product.family.csv',
        'data/product.fiber.csv',
        'data/product.gauge.csv',
        'data/product.title.csv',
        'report/ir_actions_report_templates.xml',
        'report/report_color_recipe.xml',
        'report/report_product_analysis.xml',
        'report/ir_actions_report.xml',
        'views/account_incoterms_views.xml',
        'views/account_payment_term_views.xml',
        'views/base_process_views.xml',
        'views/color_code_system_views.xml',
        'views/color_recipe_views.xml',
        'views/configurate_svg_example.xml',
        'views/lab_dev_views.xml',
        'views/product_color_views.xml',
        'views/product_template_views.xml',
        'views/res_config_settings_views.xml',
        'views/sale_order_views.xml',
        'views/lab_menu.xml',
        'views/fabric_structure_views.xml',
        'views/maintenance_equipment_views.xml',
        'views/mrp_routing_views.xml',
        'views/product_analysis_views.xml',
        'views/product_code_system_views.xml',
        'views/product_template_views.xml',
        'views/res_config_settings_views.xml',
        'views/sale_order_views.xml',
        'views/dev_menu.xml',
    ],
    
    'assets': {
        'web.assets_backend': [
            'idtx_laboratory/static/src/components/**/*',
            'idtx_laboratory/static/src/popup/**/*',
        ],
    },
}

