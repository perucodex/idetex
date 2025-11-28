# -*- coding: utf-8 -*-
{
    'name': "Sire SUNAT",

    'summary': """
        Sire SUNAT web api""",

    'description': """
        Modulo para trabajar son Sire Web API SUNAT. Acepta, remplaza la propuesta
        en la SUNAT solo para registrar en el portal.
    """,

    'author': "Codex Development",
    'website': "https://www.perucodex.com",

    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/16.0/odoo/addons/base/data/ir_module_category_data.xml
    # for the full list
    'category': 'Accounting',
    'version': '19.0.0.0',
    'license': 'LGPL-3',
    'sequence': 0,

    # any module necessary for this one to work correctly
    'depends': ['base', 'account', 'l10n_pe_edi'],

    # always loaded
    'data': [
        'security/ir.model.access.csv',
        'security/record_rule.xml',
        'views/res_config_settings_views.xml',
        'views/sire_sunat_views.xml',
    ],
    'external_dependencies': {
        'python': ['tuspy','tusclient'],
    },


}