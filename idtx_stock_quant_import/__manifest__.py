# -*- coding: utf-8 -*-
{
    'name': "Importador para Tienda",

    'summary': "Importador de Excel de Stock Quant",

    'description': """
Importa los stock quant desde un excel para tener el inventario que se enviará a la tienda
    """,

    'author': "Codex Development",
    'website': "https://www.perucodex.com",

    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/15.0/odoo/addons/base/data/ir_module_category_data.xml
    # for the full list
    'category': 'Sales',
    'version': '0.6',
    'license': 'LGPL-3',
    'sequence': 0,

    # any module necessary for this one to work correctly
    'depends': [
        'base',
        'stock',
        'idtx_laboratory',
        'idtx_mrp',          # override de create_zpl (etiqueta física del rollo)
        ],

    # always loaded
    'data': [
        'data/ir_sequence.xml',
        'security/groups.xml',
        'security/ir.model.access.csv',
        'views/stock_quant_import_views.xml',
    ],
}

