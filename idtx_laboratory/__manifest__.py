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
    'category': 'Producción Textil',
    'version': '0.1',
    'license': 'LGPL-3',

    # any module necessary for this one to work correctly
    'depends': [
            'base',
            'portal',
            'sale',
        ],

    # always loaded
    'data': [
        'security/group_lab.xml',
        'security/ir.model.access.csv',
        # Orden especial para nuevos registros
        'data/product.category.csv',
        'data/intial_company_categories.xml',
        'data/chemical_products.xml',
        'data/base_process.xml',
        'data/base_process_line.xml',
        # Fin de orden especial
        'data/color.fiber.csv',
        'data/color.intensity.csv',
        'data/color.process.type.csv',
        'data/color.range.csv',
        'data/ir_sequence.xml',
        'report/report_color_recipe.xml',
        'report/ir_actions_report.xml',
        'views/base_process_views.xml',
        'views/color_code_system_views.xml',
        'views/color_recipe_views.xml',
        'views/lab_dev_views.xml',
        'views/product_template_views.xml',
        'views/res_config_settings_views.xml',
        'views/lab_menu.xml',
    ],
    
}

