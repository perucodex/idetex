# -*- coding: utf-8 -*-
{
    'name': "Importador de Productos",

    'summary': "Importa productos de SQL",

    'description': """
Importa los productos y crea sus fichas tecnicas
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
    'depends': [
        'base',
        'idtx_laboratory',
        'idtx_product_development',
        'l10n_pe',
        'pc_l10n_pe_vat_sunat',
    ],

    # always loaded
    'data': [
        'data/cron.xml',
        # 'security/ir.model.access.csv',
        'views/product_analysis_views.xml',
        # 'views/templates.xml',
    ],
}

