# -*- coding: utf-8 -*-
{
    'name': "Planilla PE - Tareo (plantilla Excel)",
    'summary': "Cálculo de planilla peruana desde un Excel de tareo (plantilla)",
    'description': """
Modo TAREO para la planilla peruana: en vez de calcular las boletas desde las
marcaciones biométricas (hr.attendance), las cantidades del mes (días, faltas,
vacaciones, licencias, horas nocturnas, HE, tardanzas, bonos y descuentos) se
cargan desde un Excel de tareo subido al lote de nómina.

Es OPCIONAL: se activa por compañía (Ajustes ▸ Planilla por Tareo). Sin este
módulo, la planilla base (idtx_hr_payroll_pe) se calcula solo por asistencias.
    """,
    'author': "Codex Development",
    'website': "https://www.perucodex.com",
    'category': 'Payroll',
    'version': '19.0.1.0.0',
    'license': 'LGPL-3',
    'depends': [
        'idtx_hr_payroll_pe',
    ],
    'external_dependencies': {'python': ['openpyxl']},
    'data': [
        'views/hr_payslip_run_views.xml',
        'views/res_config_settings_views.xml',
    ],
    'installable': True,
    'application': False,
}
