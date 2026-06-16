# -*- coding: utf-8 -*-
{
    'name': "Actualizar DNI Empleado",

    'summary': "Obtiene los datos del empleado a partir de su DNI",

    'description': """
Agrega un botón "Actualizar DNI" en el formulario del empleado que, a partir del
N° de Identificación (DNI), consulta los datos de la persona y completa el nombre
del empleado en formato "APELLIDOS NOMBRES".
    """,

    'author': "Codex Development",
    'website': "https://www.perucodex.com",

    'category': 'Human Resources',
    'version': '19.0.0.0',
    'license': 'LGPL-3',

    'depends': [
        'hr',
    ],

    'data': [
        'views/hr_employee_views.xml',
    ],

    'installable': True,
}
