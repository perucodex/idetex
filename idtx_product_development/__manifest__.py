# -*- coding: utf-8 -*-
{
    'name': "Desarrollo de Producto",

    'summary': "Modulo para desarrollo de producto",

    'description': """
Descripción del modulo para desarrollo de producto
    """,

    'author': "Codex Development",
    'website': "https://www.perucodex.com",

    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/15.0/odoo/addons/base/data/ir_module_category_data.xml
    # for the full list
    'category': 'Manufacturing',
    'version': '0.1',
    'license': 'LGPL-3',

    # any module necessary for this one to work correctly
    'depends': [
            'base',
            'product',
            'mrp',
            'maintenance',
        ],

    # always loaded
    'data': [
        'security/group_pd.xml',
        'security/ir.model.access.csv',
        'data/ir_sequence_data.xml',
        'data/product.appearance.csv',
        'data/product.family.csv',
        'data/product.fiber.csv',
        'data/product.gauge.csv',
        'data/product.title.csv',
        'report/report_product_analysis.xml',
        'report/ir_actions_report.xml',
        'views/fabric_structure_views.xml',
        'views/maintenance_equipment_views.xml',
        'views/mrp_routing_views.xml',
        'views/product_analysis_views.xml',
        'views/product_code_system_views.xml',
        'views/product_template_views.xml',
        'views/res_config_settings_views.xml',
        'views/menu.xml',
        'views/template.xml',
    ],

}

