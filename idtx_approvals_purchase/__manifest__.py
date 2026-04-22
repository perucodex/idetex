# -*- coding: utf-8 -*-
{
    'name': "Requerimientos",

    'summary': "Requerimientos con diferente descripción",

    'description': """
Si un requerimiento tiene el mismo producto pero con diferente descripción entonces al momento
de crear la orden de compra se crean nuevas lineas y no se juntan todas en una sola.
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
    'depends': ['base', 'approvals_purchase'],

    # always loaded
    'data': [
        # 'security/ir.model.access.csv',
        'security/groups_app.xml',
        'views/approval_product_line_views.xml',
        # 'views/templates.xml',
    ],
}

