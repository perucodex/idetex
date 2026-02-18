# -*- coding: utf-8 -*-
{
    'name': "Planilla PE",

    'summary': "Planilla Localización Peruana",

    'description': """
Localización peruana para trabajar planillas de todo tipo
    """,

    'author': "Codex Development",
    'website': "https://www.perucodex.com",

    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/15.0/odoo/addons/base/data/ir_module_category_data.xml
    # for the full list
    'category': 'Payroll',
    'version': '19.0.0.0',
    'license': 'LGPL-3',

    # any module necessary for this one to work correctly
    'depends': [
        'base',
        'hr_payroll'
    ],

    # always loaded
    'data': [
        'data/hr_afp.xml',
        'data/hr_payroll_structure_type.xml',
        'data/hr_payroll_structure.xml',
        'data/hr_payslip_input_type.xml',
        'data/hr_salary_rule_category.xml',
        'data/hr_salary_rule_weekly_textil.xml',
        'data/hr_work_entry_type.xml',
        'security/ir.model.access.csv',
        'views/hr_afp_views.xml',
        'views/hr_contract_salary_views.xml',
        'views/res_config_settings_views.xml',
    ],
}

