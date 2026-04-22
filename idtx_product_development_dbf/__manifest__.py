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
    'version': '19.0.0.0',
    'license': 'LGPL-3',
    'depends': ['idtx_product_development', 'idtx_import_product'],
    'external_dependencies': {
        'python': ['dbf', 'pyodbc'],
    },
    'data': [
        'views/res_config_settings_views.xml',
        'views/technical_sheet_views.xml',
    ],
    'installable': True,
    'application': False,
}