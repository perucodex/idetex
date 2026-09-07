# -*- coding: utf-8 -*-
{
    'name': "Reporte de Existencias PdV",

    'summary': "Reporte detallado de stock con lotes, colores y referencias para el PdV",

    'description': """
Muestra un reporte unificado de existencias que incluye:
- Código y descripción del artículo
- Código y descripción del color
- Lote
- Referencia (Rollo)
- Cantidad disponible
- Ubicación
    """,

    'author': "Codex Development",
    'website': "https://www.perucodex.com",

    'category': 'Point of Sale',
    'version': '19.0.1.0.9',
    'license': 'LGPL-3',

    'depends': [
        'base',
        'stock',
        'point_of_sale',
        'idtx_pos_lot_color',
        'idtx_mrp',
        'idtx_laboratory',
    ],

    'data': [
        'security/ir.model.access.csv',
        # Setup idempotente del tag 'Muestra' para stock.scrap (asocia
        # xml_id estable al record existente, o lo crea si falta).
        'data/stock_scrap_reason_tag_data.xml',
        'views/pos_stock_report_views.xml',
    ],
    'installable': True,
    'application': False,
}
