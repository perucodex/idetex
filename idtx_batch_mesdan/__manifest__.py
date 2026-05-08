# -*- coding: utf-8 -*-
{
    'name': 'Integración Mesdan',

    'summary': 'Importación de reportes PDF desde el equipo Mesdan vía FTP',

    'description': '''
Extiende control.pedido.line para importar el reporte PDF generado por la
máquina Mesdan desde su servidor FTP y adjuntarlo al registro.
    ''',

    'author': 'Codex Development',
    'website': 'https://www.perucodex.com',

    'category': 'Uncategorized',
    'version': '19.0.0.0',
    'license': 'LGPL-3',

    'depends': [
        'idtx_batch_control',
    ],

    'data': [
        'views/control_pedido_line_views.xml',
    ],
}
