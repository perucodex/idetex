# -*- coding: utf-8 -*-
{
    'name': 'Product Development DBF Export',
    'summary': 'Exporta fichas tecnicas de desarrollo de producto a FoxPro DBF',
    'description': """
Exporta las fichas tecnicas creadas desde desarrollo de producto a las tablas DBF
de FoxPro usadas por SITPRO/Tintoreria.
    """,
    'author': 'Codex Development',
    'website': 'https://www.perucodex.com',
    'category': 'Produccion Textil',
    'version': '19.0.1.0.0',
    'license': 'LGPL-3',
    'depends': ['idtx_product_development', 'idtx_import_product', 'idtx_thread_codigo'],
    'external_dependencies': {
        'python': ['dbf', 'pyodbc'],
    },
    'data': [
        'security/ir.model.access.csv',
        'data/cron.xml',
        'views/res_config_settings_views.xml',
        'views/technical_sheet_views.xml',
        'views/mrp_base_process_views.xml',
        'views/texplus_tipart_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'idtx_product_development_dbf/static/src/js/technical_sheet_export_prompt.js',
        ],
    },
    'installable': True,
    'application': False,
}