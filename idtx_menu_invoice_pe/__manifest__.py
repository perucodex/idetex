# -*- coding: utf-8 -*-
{
    'name': "Boleta de Menú",

    'summary': "Boletas de menú por empleado",

    'description': """
Genera las boletas de los menús consumidos en la fecha.
    """,

    'author': "Codex Development",
    'website': "https://www.perucodex.com",

    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/15.0/odoo/addons/base/data/ir_module_category_data.xml
    # for the full list
    'category': 'Accounting',
    'version': '19.0.0.0',
    'license': 'LGPL-3',

    # any module necessary for this one to work correctly
    'depends': [
        'base',
        'account',
        'portal',
        'l10n_pe',
    ],

    # always loaded
    'data': [
        'data/ir_sequence.xml',
        'security/group_menu_invoice.xml',
        'security/ir.model.access.csv',
        'views/menu_invoice_views.xml',
        'views/menu_invoice_menu.xml',
    ],
}

