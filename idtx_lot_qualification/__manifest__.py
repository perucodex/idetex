# -*- coding: utf-8 -*-
{
    'name': "Calificacion de Lote",

    'summary': "Calificación de lote de hilado",

    'description': """
Califica los lotes por intensidad de color y defectos
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
    'depends': [
        'idtx_laboratory',
        'idtx_product_development',
        'idtx_sale_order',
    ],

    # always loaded
    'data': [
        # 'security/ir.model.access.csv',
        'views/mrp_production_views.xml',
        'views/stock_lot_views.xml',
        # 'views/templates.xml',
    ],
}

