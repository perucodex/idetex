# -*- coding: utf-8 -*-
{
    'name': "Plan General",

    'summary': "Plan General de Producción Textil",

    'description': """
Módulo de Plan General de Producción para empresas textiles.
Dashboard con KPIs, gráficos de estado, clientes, áreas y procesos.
    """,

    'author': "Codex Development",
    'website': "https://www.perucodex.com",

    'category': 'Manufacturing',
    'version': '0.1',
    'license': 'LGPL-3',
    'sequence': 55,
    'application': True,

    'depends': [
        'mrp',
        'idtx_batch_control',
        'maintenance',
        'hr_maintenance',
    ],

    'data': [
        'security/ir.model.access.csv',
        'views/mrp_menu.xml',
    ],

    'assets': {
        'web.assets_backend': [
            'idtx_plan_general/static/src/dashboard/dashboard.css',
            'idtx_plan_general/static/src/dashboard/dashboard.xml',
            'idtx_plan_general/static/src/dashboard/dashboard.js',
        ],
    },
}
