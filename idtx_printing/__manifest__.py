# -*- coding: utf-8 -*-
{
    'name': "Estampados",

    'summary': "Módulo de control de estampados",

    'description': """
Producción y control de estampados textiles.
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
    'depends': ['base', 'idtx_laboratory'],

    # always loaded
    'data': [
        'security/group_print.xml',
        'security/ir.model.access.csv',
        'data/ir_sequence.xml',
        'views/printing_design_views.xml',
        'views/res_config_settings_views.xml',
        'views/print_menu.xml',
    ],
}

