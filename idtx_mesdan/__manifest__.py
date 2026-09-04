# -*- coding: utf-8 -*-
{
    'name': 'Integración Mesdan (Partidas Odoo)',

    'summary': 'Adjunta a la partida los reportes PDF del equipo Mesdan leídos del NAS',

    'description': '''
Extiende mrp.workorder.batch (partidas de idtx_mrp) para importar los reportes
PDF generados por el equipo Mesdan. Reemplaza a idtx_batch_mesdan, que colgaba
los PDF de las partidas TEXPLUS (control.pedido.line).

El HMI del Mesdan escribe los PDF en el NAS (share 172.16.64.6:/odoo, carpeta
MESDAN/AA_MM_DD/) y Odoo los lee desde un mount NFS del mismo share. El nombre
del archivo lleva el código de partida que el operador escribió en el HMI
(Rep_<x>_<PARTIDA>_D<fecha>_T<hora>.pdf); ese código se resuelve contra el
nombre de la partida Odoo (p. ej. WB00057 o WB00057-A). Un cron horario adjunta
los reportes nuevos; el NAS conserva el histórico y Odoo nunca borra nada.

Requiere que el servidor Odoo tenga montado el share:
    172.16.64.6:/odoo  /mnt/nas_mesdan_reports  nfs  ro,nolock,soft,timeo=20,_netdev,bg  0  0

Parámetros del sistema (Ajustes > Técnico > Parámetros del sistema):
    idtx_mesdan.reports_dir      carpeta de reportes (por defecto /mnt/nas_mesdan_reports/MESDAN)
    idtx_mesdan.host             IP del Mesdan para reparar su montaje NFS por telnet
    idtx_mesdan.telnet_user      usuario telnet (root)
    idtx_mesdan.telnet_password  clave telnet; vacía = no se intenta la reparación
    ''',

    'author': 'Codex Development',
    'website': 'https://www.perucodex.com',
    'category': 'Manufacturing/Quality',
    'version': '19.0.1.0.0',
    'license': 'LGPL-3',

    'depends': [
        'mail',
        'idtx_mrp',
    ],

    'data': [
        'data/config_parameters.xml',
        'data/ir_cron.xml',
        'views/mrp_workorder_batch_views.xml',
    ],
    'installable': True,
    'application': False,
}
