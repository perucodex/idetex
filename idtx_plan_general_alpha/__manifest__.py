# -*- coding: utf-8 -*-
{
    'name': "Plan General Alpha",

    'summary': "Planeamiento General de Produccion Textil",

    'description': """
Modulo de Planeamiento General Alpha.
Usa las vistas nativas de Odoo (kanban, lista, calendario, graph, pivot)
sobre los modelos existentes de Control de Pedidos, MRP y Ventas.
    """,

    'author': "Codex Development",
    'website': "https://www.perucodex.com",

    'category': 'Manufacturing',
    'version': '0.2',
    'license': 'LGPL-3',
    'sequence': 54,
    'application': True,
    'icon': '/idtx_plan_general_alpha/static/description/icon.svg',

    'post_init_hook': 'post_init_hook',

    'depends': [
        'mrp',
        'mrp_workorder',
        'sale_management',
        'maintenance',
        'board',
        'idtx_mrp',
        'idtx_batch_control',
        'idtx_maintenance',
    ],

    'assets': {
        'web.assets_backend': [
            'idtx_plan_general_alpha/static/src/nav_overflow.scss',
            'idtx_plan_general_alpha/static/lib/apexcharts.min.js',
            'idtx_plan_general_alpha/static/src/dashboard_alpha/dashboard_alpha.scss',
            'idtx_plan_general_alpha/static/src/dashboard_alpha/dashboard_alpha.js',
            'idtx_plan_general_alpha/static/src/dashboard_alpha/dashboard_alpha.xml',
            'idtx_plan_general_alpha/static/src/machine_floor/machine_floor.scss',
            'idtx_plan_general_alpha/static/src/machine_floor/machine_floor.xml',
            'idtx_plan_general_alpha/static/src/machine_floor/machine_floor.js',
        ],
        'web.assets_web_dark': [
            'idtx_plan_general_alpha/static/src/dashboard_alpha/dashboard_alpha.dark.scss',
        ],
    },

    'data': [
        'security/ir.model.access.csv',
        'views/plan_dashboard_views.xml',
        'views/plan_tablas_views.xml',
        'views/plan_beta_views.xml',
        'views/plan_production_views.xml',
        'views/plan_workorder_views.xml',
        'views/plan_sale_views.xml',
        'views/plan_config_views.xml',
        'views/plan_floor_views.xml',
        'views/plan_alpha_menu.xml',
    ],
}
