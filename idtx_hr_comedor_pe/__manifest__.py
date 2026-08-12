# -*- coding: utf-8 -*-
{
    'name': "Descuento Comedor (PE)",
    'summary': "Trae el consumo del comedor (BD MySQL) y lo descuenta en la planilla",
    'description': """
Módulo SEPARADO (desinstalable a futuro) que calcula el "Descuento Comedor" de
la planilla peruana a partir de la base de datos MySQL del comedor.

Por cada recibo, consulta la tabla estado_diario por el DNI del trabajador en la
ventana de corte (día configurable, p. ej. del 25 del mes anterior al 25 del mes
del recibo), items 2/3/20 no pagados, suma el campo 'precio' y resta el subsidio
de la empresa por cada registro de item 2 o 3 (subsidio configurable por
parámetro). El resultado alimenta el input DSCT_COMEDOR del recibo, que la regla
"Descuento Comedor" de idtx_hr_payroll_pe ya consume.

Al desinstalar este módulo, el concepto "Descuento Comedor" sigue existiendo en
la planilla y puede cargarse manualmente con el input DSCT_COMEDOR.
    """,
    'author': "Codex Development",
    'website': "https://www.perucodex.com",
    'category': 'Payroll',
    'version': '19.0.0.0',
    'license': 'LGPL-3',
    'depends': ['idtx_hr_payroll_pe'],
    'data': [
        'security/ir.model.access.csv',
        'data/comedor_parameters.xml',
        'views/comedor_corte_views.xml',
    ],
    'installable': True,
}
