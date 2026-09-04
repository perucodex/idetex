# -*- coding: utf-8 -*-
{
    'name': "Plan General Alpha",

    'summary': "Planeamiento General de Produccion Textil",

    'description': """
Módulo de Planeamiento General Alpha.

Tablero de planeamiento (OWL) sobre pedidos de venta, piso de máquinas por centro
de trabajo (mantenimiento + órdenes de trabajo) y vistas nativas de producción,
órdenes de trabajo y ventas. Reconstruido sobre datos de Odoo: se retiró la
dependencia de SITPRO/TEXPLUS (2026-09).

Pendiente (fase 2): la pantalla de Planning (Gantt) que programaba las partidas
TEXPLUS se reconstruirá sobre las partidas de Odoo (mrp.workorder.batch).
    """,

    'author': "Codex Development",
    'website': "https://www.perucodex.com",

    'category': 'Manufacturing',
    'version': '19.0.1.0.0',
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
            'idtx_plan_general_alpha/static/src/machine_floor/machine_floor.dark.scss',
        ],
    },

    'data': [
        'security/ir.model.access.csv',
        'views/plan_dashboard_views.xml',
        'views/plan_production_views.xml',
        'views/plan_workorder_views.xml',
        'views/plan_sale_views.xml',
        'views/plan_config_views.xml',
        'views/plan_floor_views.xml',
        'views/plan_alpha_menu.xml',
    ],
    'installable': True,
}
