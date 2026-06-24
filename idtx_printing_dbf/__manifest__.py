# -*- coding: utf-8 -*-
{
    'name': "Estampados — Reporte SITPRO",

    'summary': "Reporte de líneas de estampado (rotativo/digital) desde SITPRO",

    'description': """
Reporte de kilaje de productos con fase de estampado, a nivel de línea de
pedido (vta_det_pedido). Cada línea trae su tipo de estampado (rotativo/digital)
derivado del código de diseño (CODDISENO) o de la descripción; el tipo es
editable y, una vez editado a mano, el cron ya no lo sobreescribe. Las líneas
despachadas se pueden archivar para sacarlas del reporte. El reporte agrupa por
tipo de estampado, cliente y pedido. Los datos se sincronizan en el mismo cron
de idtx_batch_control (hook _sync_extra_data en control.pedido).
    """,

    'author': "Codex Development",
    'website': "https://www.perucodex.com",

    'category': 'Manufacturing',
    'version': '19.0.0.0',
    'license': 'LGPL-3',

    'depends': [
        'idtx_batch_control',
        'idtx_printing',
        'idtx_product_development',
        'idtx_import_product',
    ],

    'data': [
        'security/ir.model.access.csv',
        'views/printing_kilos_views.xml',
        'views/printing_kilos_menu.xml',
    ],
}
