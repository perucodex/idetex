# -*- coding: utf-8 -*-
{
    "name": "Thread Bag Control",
    "summary": "Control individual de bolsas de hilo (peso neto, conos) por lote",
    "description": """
Control de hilo a nivel de bolsa física.
- Cada bolsa es una unidad con su correlativo único, lote, conos y PESO NETO propio.
- Kg de un lote = suma de pesos netos de sus bolsas disponibles.
- Importación del packing list (Excel) para dar de alta las bolsas.
- Consumo en producción/transferencias eligiendo bolsas por correlativo.
- Habilitado para productos marcados como is_thread.
    """,
    "author": "Codex Development",
    "website": "https://www.perucodex.com",
    "category": "Inventory",
    "version": "19.0.3.0.0",
    "license": "LGPL-3",
    "depends": [
        "mrp",
        "stock",
        "idtx_lot_qualification",
        "idtx_product_development",
    ],
    "data": [
        "security/ir.model.access.csv",
        "security/thread_bag_security.xml",
        "views/thread_bag_views.xml",
        "views/thread_bag_consume_wizard_views.xml",
        "views/stock_views.xml",
    ],
    "installable": True,
    "application": False,
}
