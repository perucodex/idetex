# -*- coding: utf-8 -*-
{
    'name': "Mrp Shop Floor Textil",

    'summary': "Módulo de producción textil para planta",

    'description': """
Desde el modulo Shop Floor podemos hacer el ingreso de rollos y rectilíneos para poder 
luego armar las partidas
    """,

    'author': "Codex Development",
    'website': "https://www.perucodex.com",

    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/15.0/odoo/addons/base/data/ir_module_category_data.xml
    # for the full list
    'category': 'Producción Textil',
    'version': '0.1',
    'license': 'LGPL-3',

    # any module necessary for this one to work correctly
    'depends': [
            'idtx_sale_order',
        ],

    # always loaded
    'data': [
        'data/hr_department.xml',
        'security/ir.model.access.csv',
        'views/batch_registry_views.xml',
        'views/maintenance_equipment_views.xml',
        'views/mrp_menu.xml',
        'views/mrp_workorder_batch_views.xml',
    ],
    
    'assets': {
        'web.assets_backend': [
            'idtx_mrp_shop/static/src/shop/**/*',
            # 'idtx_mrp_shop/static/src/images/**/*',
        ],
    },
}

