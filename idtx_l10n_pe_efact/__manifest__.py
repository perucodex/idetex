# -*- coding: utf-8 -*-
{
    'name': "PE: Integración OSE Efact",

    'summary': "OSE Efact",

    'description': """
Facturación electrónica con OSE Efact
    """,

    'author': "Codex Development",
    'website': "https://www.perucodex.com",

    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/15.0/odoo/addons/base/data/ir_module_category_data.xml
    # for the full list
    'category': 'Uncategorized',
    'version': '0.1',
    'license': 'LGPL-3',
    'sequence': 0,

    # any module necessary for this one to work correctly
    'depends': [
        'base',
        'l10n_pe_edi',
        'idtx_sale_sitpro',
        ],

    # always loaded
    'data': [
        'data/paperformat.xml',
         'views/report_invoice.xml',
        'views/account_move_views.xml',
        'views/account_payment_term_views.xml',
        'views/sale_order_views.xml',
        'views/res_company_views.xml',
        # 'security/ir.model.access.csv',
        # 'views/views.xml',
        # 'views/templates.xml',
    ],
}

