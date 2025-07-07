# -*- coding: utf-8 -*-
{
    'name': "Desarrollo de Producto",

    'summary': "Modulo para desarrollo de producto",

    'description': """
Descripción del modulo para desarrollo de producto
    """,

    'author': "Codex Development",
    'website': "https://www.perucodex.com",

    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/15.0/odoo/addons/base/data/ir_module_category_data.xml
    # for the full list
    'category': 'Manufacturing',
    'version': '0.1',
    'license': 'LGPL-3',

    # any module necessary for this one to work correctly
    'depends': [
            'base',
            'product',
            'mrp',
        ],

    # always loaded
    'data': [
        'security/ir.model.access.csv',
        'views/mrp_routing_views.xml',
        'views/product_template_views.xml',
    ],
}

