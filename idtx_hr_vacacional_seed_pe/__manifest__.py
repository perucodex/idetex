# -*- coding: utf-8 -*-
{
    'name': 'Planilla PE - Seed Vacacional (temporal)',
    'version': '19.0.1.0.0',
    'category': 'Human Resources/Payroll',
    'summary': 'Carga el histórico de variables para la remuneración vacacional '
               'al implementar; desinstalable a los 6 meses.',
    'description': """
Módulo TEMPORAL de implementación
=================================
Permite cargar, por empleado y por mes, el histórico de variables
(HE 25% + HE 35% + bonificación nocturna + prima textil) del sistema anterior,
para que el cálculo de la remuneración vacacional disponga del promedio de los
6 meses previos antes de tener 6 boletas reales en Odoo.

Solo siembra los meses ANTERIORES al go-live (una fila por mes). Conforme se
generan boletas reales, éstas reemplazan al seed; cuando ya existen 6 boletas
reales el seed deja de usarse y este módulo se puede DESINSTALAR sin afectar
el cálculo.

Conecta con `idtx_hr_payroll_pe` mediante el hook `_pe_vacacional_seed_for_period`.
""",
    'author': 'IDETEX',
    'depends': ['idtx_hr_payroll_pe'],
    'data': [
        'security/ir.model.access.csv',
        'views/vacacional_seed_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
