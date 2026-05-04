# -*- coding: utf-8 -*-
{
    "name": "Thread Lot Bag Control",
    "summary": "Control bags, cones and cone weight by lot for thread products",
    "description": """
Thread inventory control by lot.
- Register bags received/sent/remaining by lot
- Track cone quantity per bag
- Track cone weight and total weight
- Enabled only for products marked as is_thread
    """,
    "author": "Codex Development",
    "website": "https://www.perucodex.com",
    "category": "Inventory",
    "version": "19.0.1.0.0",
    "license": "LGPL-3",
    "depends": [
        "mrp",
        "stock",
        "idtx_lot_qualification",
        "idtx_product_development",
    ],
    "data": [
        "security/ir.model.access.csv",
        "data/ir_sequence.xml",
        "views/thread_lot_control_views.xml",
        "views/stock_picking_views.xml",
        "views/stock_lot_views.xml",
        "views/mrp_production_thread_second_quality_wizard_views.xml",
        "views/stock_move_import_packing_wizard_views.xml",
        "views/stock_picking_import_packing_wizard_views.xml",
    ],
    "installable": True,
    "application": False,
}
