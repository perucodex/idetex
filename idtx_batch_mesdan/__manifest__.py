# -*- coding: utf-8 -*-
{
    'name': 'Integración Mesdan',

    'summary': 'Importación de reportes PDF del Mesdan desde el NAS (NFS)',

    'description': '''
Extiende control.pedido.line para importar los reportes PDF generados por la
máquina Mesdan. Los PDFs son escritos por el HMI directamente al NAS
(montado por NFS en el equipo Mesdan), y Odoo los lee desde otro mount NFS
del mismo share. Un cron horario adjunta a cada partida los reportes
nuevos. El NAS conserva el archivo histórico — Odoo nunca borra del NAS.

Requiere que el server Odoo tenga montado /mnt/nas_mesdan_reports:
    172.16.64.6:/odoo  /mnt/nas_mesdan_reports  nfs  ro,nolock,soft,timeo=20,_netdev,bg  0  0
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
        'data/ir_cron.xml',
        'views/control_pedido_line_views.xml',
    ],
}
