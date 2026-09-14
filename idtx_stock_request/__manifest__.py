# Copyright 2017-2021 ForgeFlow, S.L.
# Copyright 2026 Codex Development
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl.html).

{
    "name": "Requerimientos de almacén",
    "summary": "Requerimientos internos de productos al almacén: cada requerimiento "
    "genera el traslado interno listo para que almacén lo atienda",
    "description": """
Basado en el módulo OCA ``stock_request`` (ForgeFlow, rama 19.0) renombrado a
``idtx_stock_request`` y adaptado para IDETEX:

* Requerimientos (varios productos por documento) activados por defecto.
* Si no se elige ruta y el destino no es Existencias, se crea un traslado interno
  directo desde Existencias del almacén (no dispara Comprar/Fabricar del producto).
* Solicitante y observaciones visibles en el requerimiento y copiados al traslado.
* Menú para almacén en Inventario > Operaciones.
* Destino por defecto configurable por almacén; nunca Existencias (origen del traslado).
* Un solo traslado por requerimiento con todas sus líneas (referencia de stock propia).
* Botón Imprimir: PDF «Requerimiento de productos» con el formato papel de IDETEX.
* Ajustes solo con opciones disponibles en este repositorio.
""",
    "version": "19.0.1.3.0",
    "license": "LGPL-3",
    "author": "Codex Development, ForgeFlow, Odoo Community Association (OCA)",
    "website": "https://www.perucodex.com",
    "category": "Inventory/Inventory",
    "depends": ["stock"],
    "data": [
        "security/stock_request_security.xml",
        "security/ir.model.access.csv",
        "data/stock_request_sequence_data.xml",
        "views/product.xml",
        "views/stock_request_views.xml",
        "views/stock_request_allocation_views.xml",
        "views/stock_move_views.xml",
        "views/stock_picking_views.xml",
        "reports/report_stock_request_order.xml",
        "views/stock_request_order_views.xml",
        "views/res_config_settings_views.xml",
        "views/stock_request_menu.xml",
        "views/stock_warehouse_views.xml",
    ],
    "application": True,
    "installable": True,
}
