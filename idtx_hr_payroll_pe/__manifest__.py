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
    'version': '19.0.1.0.0',
    'license': 'LGPL-3',

    # any module necessary for this one to work correctly
    'depends': [
        'base',
        'hr_payroll'
    ],

    'post_init_hook': 'post_init_hook',

    # always loaded
    'data': [
        'data/resource_calendar.xml',
        'data/hr_rule_parameter.xml',
        'data/hr_afp.xml',
        'data/hr_payroll_structure_type.xml',
        'data/hr_work_entry_type.xml',
        'data/hr_leave_type.xml',
        'data/hr_payroll_structure.xml',
        'data/hr_payslip_input_type.xml',
        'data/hr_salary_rule_category.xml',
        'data/hr_salary_rule_general.xml',
        'data/hr_salary_rule_benefits.xml',
        'data/hr_salary_rule_liquidation.xml',
        'data/hr_salary_rule_obrero.xml',
        'data/hr_salary_rule_agrario.xml',
        'security/ir.model.access.csv',
        'report/hr_payslip_report.xml',
        'views/hr_afp_views.xml',
        'views/hr_contract_salary_views.xml',
        'views/res_config_settings_views.xml',
        'views/hr_payslip_run_views.xml',
        'views/payroll_export_views.xml',
    ],
}

