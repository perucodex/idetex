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
    'version': '19.0.0.0',
    'license': 'LGPL-3',

    # any module necessary for this one to work correctly
    'depends': ['base', 'web', 'idtx_batch_quality', 'idtx_printing'],

    # always loaded
    'data': [
        'data/deffects.xml',
        'views/control_apariencia_defecto_views.xml',
        'views/control_pedido_line_views.xml',
        'views/printing_defect_screen.xml',
    ],

    'assets': {
        'web.assets_backend': [
            'idtx_batch_printing/static/src/defect_screen/quality_defect_screen.js',
            'idtx_batch_printing/static/src/defect_screen/quality_defect_screen.xml',
            'idtx_batch_printing/static/src/defect_screen/quality_defect_screen.scss',
        ],
    },
}

