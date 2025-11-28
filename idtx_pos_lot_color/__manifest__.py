# -*- coding: utf-8 -*-
{
    'name': "Color en PdV",

    'summary': "Codigo y nombre de color en PdV",

    'description': """
Agrega el codigo de color y el nombre del color en la pantalla de despacho del PdV
    """,

    'author': "Codex Development",
    'website': "https://www.perucodex.com",

    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/15.0/odoo/addons/base/data/ir_module_category_data.xml
    # for the full list
    'category': 'Uncategorized',
    'version': '19.0.0.0',
    'license': 'LGPL-3',

    # any module necessary for this one to work correctly
    'depends': [
        'base',
        'idtx_pos_receipt'
        ],

    # always loaded
    'data': [
        # 'security/ir.model.access.csv',
        # 'views/views.xml',
        # 'views/templates.xml',
    ],
    'assets': {
        'point_of_sale._assets_pos': [
            'idtx_pos_lot_color/static/src/**/*',
        ],
    },
}

