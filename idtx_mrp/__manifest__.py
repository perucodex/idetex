# -*- coding: utf-8 -*-
{
    'name': "Mrp Base Textil",

    'summary': "Modulo base para mrp textil",

    'description': """
Módulo base para los desarrollos de producción para empresas textiles
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
            'base',
            'portal',
            'mrp_workorder',
            'mrp_maintenance',
        ],

    # always loaded
    'data': [
        'data/ir_module_category_data.xml',
        'data/ir_sequence.xml',
        'data/mrp.workcenter.csv',
        'security/ir.model.access.csv',
        'views/mrp_production_roll_views.xml',
        'views/mrp_production_views.xml',
        'views/mrp_routing_views.xml',
        'views/mrp_workorder_batch_views.xml',
        'views/mrp_workorder_roll_views.xml',
        'views/mrp_workorder_views.xml',
        'views/res_company_views.xml',
        'views/scale_registry_views.xml',
        'views/stock_quant_views.xml',
        'wizard/add_production_roll.xml',
        'wizard/additional_workorder_views.xml',
        'wizard/split_roll_views.xml',
        'views/mrp_menu.xml',
    ],
    'demo': [
        'demo/mrp.routing.workcenter.operation.csv',
    ],
}

