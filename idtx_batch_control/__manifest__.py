# -*- coding: utf-8 -*-
{
    'name': "Control de Pedidos",

    'summary': "Control de perdidos para IDETEX",

    'description': """
Control de pedidos desde SITPRO y TEXTPLUS, integración para obtener información de bases de datos
de foxpro (dbf) SITPRO y conección con MSSql server para obtener data del TEXPLUS
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
    'depends': ['base'],

    # always loaded
    'data': [
        'security/ir.model.access.csv',
        # 'views/views.xml',
        'views/control_pedido_views.xml',
    ],
}

