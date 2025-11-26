# -*- coding: utf-8 -*-
{
    'name': "Idetex Maintenance",

    'summary': "Additional fields for maintenance",

    'description': """
Additional fields for maintenance to manage equipment
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
    'depends': ['maintenance'],

    # always loaded
    'data': [
        # 'security/ir.model.access.csv',
        'views/maintenance_equipment_views.xml',
    ],
}

