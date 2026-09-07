# -*- coding: utf-8 -*-
{
    # Nombre comercial del módulo
    'name': 'Ventas POS Tienda Idetex',
    
    # Versión del módulo (Sigue el estándar de Odoo)
    'version': '1.0.27',
    
    # Categoría dentro de las aplicaciones de Odoo
    'category': 'Point of Sale',
    
    'author': "Ricardo Marcelo",
    
    # Resumen rápido de la funcionalidad
    'summary': 'Sustituye botones de productos por lista detallada de existencias.',
    
    # Módulos de los que depende para funcionar correctamente
    'depends': [
        'point_of_sale',         # El módulo base del PdV
        'idtx_pos_report_stock', # El reporte técnico de stock
        'idtx_pos_lot_color',    # Gestión de colores y lotes
        'idtx_lot_report_invoice', # Campo idtx_grouped_lot_ids en account.move.line + PDF
        'l10n_pe_pos',           # Localización PE del POS (Consumidor Final, isPeruvianCompany)
    ],
    
    # Archivos de datos que se cargan al instalar el módulo (Seguridad, XMLs de servidor)
    'data': [
        'security/ir.model.access.csv',
        'wizard/pos_roll_return_wizard_views.xml',
        'wizard/pos_roll_split_wizard_views.xml',
        'wizard/pos_roll_split_revert_wizard_views.xml',
        'views/pos_roll_return_views.xml',
        'views/stock_lot_lineage_views.xml',
        # Vista heredada que reemplaza reserved_by_order_id por su label legible
        'views/pos_stock_report_muestras_views.xml',
    ],
    
    # Activos de la interfaz (JavaScript, CSS, Plantillas XML)
    'assets': {
        'point_of_sale._assets_pos': [
            # Insertamos el patch JUSTO ANTES del archivo de pos_settle_due que provoca
            # el conflicto. Así el monkey-patch del registry queda activo en el momento
            # exacto en que pos_settle_due intenta su registración duplicada.
            # No usamos 'prepend' porque eso colocaría el archivo antes del preamble del
            # module loader (rompe odoo.define).
            ('before', 'pos_settle_due/static/src/app/views/view_dialogs/select_create_dialog.js',
                       'idtx_pos_sale_idetex/static/src/_compat/dialogs_registry_idempotent.js'),
            # Resto de la aplicación POS
            'idtx_pos_sale_idetex/static/src/app/**/*',
        ],
        # Assets para el BACKEND (vista de Existencias PdV en backend, no en POS)
        # El patch del SearchBar parsea QR GS1 escaneados en la barra de búsqueda.
        'web.assets_backend': [
            'idtx_pos_sale_idetex/static/src/backend/**/*',
        ],
    },
    
    # Indica si el módulo se puede instalar
    'installable': True,
    
    # Indica si es una aplicación principal (en este caso es una extensión)
    'application': False,
    
    # Licencia bajo la que se distribuye el código
    'license': 'LGPL-3',
}
