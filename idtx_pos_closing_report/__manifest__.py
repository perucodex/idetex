# -*- coding: utf-8 -*-
{
    'name': "Reporte Cierre y Control de Caja",

    'summary': "Reporte detallado de ventas y movimientos de caja para TPV (PDF e Interactivo)",

    'description': """
Este módulo implementa el 'Reporte de Cierre y Control de Caja' solicitado, ofreciendo dos vistas principales:
1. Una tabla interactiva en Odoo (Vista Lista) con columnas detalladas (Kilos, Producto, Color, Partida, Referencia, Lote, Precios, Pagos).
2. Un reporte PDF en formato horizontal (Landscape) para impresión de auditoría.

El proceso de generación consolida la información de las órdenes de venta del TPV junto con los movimientos manuales de efectivo (ingresos/egresos) realizados en la sesión, calculando un saldo final proyectado.
    """,

    'author': "Codex Development",
    'website': "https://www.perucodex.com",

    'category': 'Point of Sale',
    'version': '19.0.0.1',
    'license': 'LGPL-3',

    'depends': [
        'point_of_sale',
        'idtx_pos_lot_color',
        'idtx_pos_receipt',
    ],

    'data': [
        'security/ir.model.access.csv',
        'report/pos_closing_report_paperformat.xml',
        'wizard/pos_closing_report_wizard_views.xml',
        'views/pos_closing_report_line_views.xml',
        'report/pos_closing_report_actions.xml',
        'report/pos_closing_report_templates.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'idtx_pos_closing_report/static/src/js/pos_closing_report_list_view.js',
        ],
    },
    'installable': True,
    'auto_install': False,
}
