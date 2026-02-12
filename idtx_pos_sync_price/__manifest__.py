# -*- coding: utf-8 -*-
{
    'name': "Sincroniza precio en PdV",

    'summary': "Sincroniza los precios del PdV para productos con mismo codigo y color",

    'description': """
Sincroniza los precios del PdV para productos con mismo codigo y color de lote.
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
        'point_of_sale',
        'idtx_pos_lot_color',
    ],

    'assets': {
        'point_of_sale._assets_pos': [
            'idtx_pos_sync_price/static/src/js/pos_sync_price_by_code_color.js',
        ],
    },
    'installable': True,
}

