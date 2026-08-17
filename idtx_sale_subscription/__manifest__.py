# -*- coding: utf-8 -*-
{
    'name': 'IDTX: Mejoras a Suscripciones',
    'summary': 'Mejoras a las suscripciones de venta (formato de periodo en '
               'la factura, entre otras).',
    'description': """
Módulo contenedor de las mejoras de IDEAS TEXTILES a las suscripciones de
venta (sale_subscription).

Primera mejora: opción en Ajustes → Ventas → Facturación para elegir cómo
se describe el periodo en la línea de la factura que genera el cron de
suscripciones:

- Rango de fechas (por defecto, comportamiento estándar): "1 mes
  14/08/2026 hasta 13/09/2026".
- Periodo mensual: "Periodo Agosto 2026".
    """,
    'author': "IDEAS TEXTILES",
    'category': 'Sales/Subscriptions',
    'version': '19.0.1.0.0',
    'license': 'LGPL-3',
    'depends': ['sale_subscription'],
    'data': [
        'views/res_config_settings_views.xml',
    ],
    'installable': True,
}
