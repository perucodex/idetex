# -*- coding: utf-8 -*-
{
    'name': "new_module",

    'summary': "Short (1 phrase/line) summary of the module's purpose",

    'description': """
Long description of module's purpose
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
        'security/ir.model.access.csv',
        'data/color.fiber.csv',
        'data/color.intensity.csv',
        'data/color.process.type.csv',
        'data/color.range.csv',
        'data/ir_sequence.xml',
        'views/base_process_views.xml',
        'views/color_code_system_views.xml',
        'views/color_recipe_views.xml',
        'views/lab_dev_views.xml',
        'views/product_color_views.xml',
        'views/sale_order_line_views.xml',
        'views/menu.xml',
    ],
}

