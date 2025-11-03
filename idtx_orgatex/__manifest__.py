# -*- coding: utf-8 -*-
{
    'name': "Integración Orgatex",

    'summary': "Modulo de integración con Orgatex",

    'description': """
Gestión de recetas e integración con sistema textil Orgatex, proyecciones y kpi's
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
    'depends': ['idtx_laboratory'],

    # always loaded
    'data': [
        'security/group_orgatex.xml',
        # 'security/ir.model.access.csv',
        'views/orgatex_menu.xml',
    ],
}

