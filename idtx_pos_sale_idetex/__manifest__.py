# -*- coding: utf-8 -*-
{
    # Nombre comercial del módulo
    'name': 'Ventas POS Tienda Idetex',
    
    # Versión del módulo (Sigue el estándar de Odoo)
    'version': '1.0',
    
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
    ],
    
    # Archivos de datos que se cargan al instalar el módulo (Seguridad, XMLs de servidor)
    'data': [
        'security/ir.model.access.csv',
    ],
    
    # Activos de la interfaz (JavaScript, CSS, Plantillas XML)
    'assets': {
        'point_of_sale._assets_pos': [
            # Cargamos todos los archivos JS, SCSS y XML dentro de static/src/app/
            'idtx_pos_sale_idetex/static/src/app/**/*',
        ],
    },
    
    # Indica si el módulo se puede instalar
    'installable': True,
    
    # Indica si es una aplicación principal (en este caso es una extensión)
    'application': False,
    
    # Licencia bajo la que se distribuye el código
    'license': 'LGPL-3',
}
