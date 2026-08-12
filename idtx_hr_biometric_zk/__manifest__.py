# -*- coding: utf-8 -*-
{
    'name': "Integración Biométrico ZKTeco (PE)",
    'summary': "Sincroniza las marcaciones de relojes ZKTeco (TCP 4370) hacia hr.attendance",
    'description': """
Integra los relojes biométricos ZKTeco (MB560, SilkFP, etc.) con Odoo.
Se conecta a cada equipo por su IP y puerto (4370) usando el protocolo ZKTeco
(librería pyzk), descarga las marcaciones, las empareja en entrada/salida por
día y crea/actualiza los registros de Asistencia (hr.attendance). El mapeo
usuario del reloj -> empleado se hace por el DNI (User ID = documento).

Con las asistencias en Odoo, la planilla peruana calcula automáticamente las
tardanzas y las horas extra (modelo híbrido).
    """,
    'author': "Codex Development",
    'website': "https://www.perucodex.com",
    'category': 'Human Resources/Attendances',
    'version': '19.0.0.0',
    'license': 'LGPL-3',
    'depends': ['hr_attendance', 'hr_holidays'],
    'external_dependencies': {'python': ['zk']},
    'data': [
        'security/ir.model.access.csv',
        'security/zk_security.xml',
        'views/zk_device_views.xml',
        'views/zk_review_views.xml',
        'data/ir_cron.xml',
    ],
    'application': False,
    'installable': True,
}
