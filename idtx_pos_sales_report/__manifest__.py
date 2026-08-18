# -*- coding: utf-8 -*-
{
    # Nombre visible del módulo
    'name': 'Reporte Ventas Tienda',

    # Resumen corto que aparece en la lista de aplicaciones
    'summary': 'Reporte de ventas del POS por tipo de comprobante (Factura, Boleta, Sin comprobante)',

    'description': """
Reporte de Ventas Tienda
========================
Vista de solo lectura (SQL) con una fila por venta del Punto de Venta,
clasificada por tipo de comprobante:

* Factura electrónica (código SUNAT 01)
* Boleta electrónica  (código SUNAT 03)
* Nota de crédito     (código SUNAT 07/08)
* Sin comprobante     (venta con PROFORMA, sin documento electrónico)

Incluye subtotal, IGV, total, cliente con RUC/DNI, serie y número del
comprobante, estado de envío a SUNAT, sesión, caja y vendedor.
Vistas: lista con totales, tabla dinámica (pivot) y gráfico.
Menú: Punto de Venta → Informes → Ventas Tienda.
""",

    'author': 'IDETEX - Sistemas',
    'category': 'Sales/Point of Sale',
    'version': '19.0.1.0.0',

    # Dependencias: POS (pedidos), account_edi (estado SUNAT del comprobante),
    # l10n_latam_invoice_document (tipos de documento 01/03/07/08),
    # idtx_pos_report_stock (para reubicar su menú "Existencias PdV"),
    # pos_enterprise (para reordenar su menú "Tiempo de preparación"),
    # idtx_pos_sale_idetex (columna color_name en pos.order.line, usada por
    # el reporte "Ventas por Producto")
    'depends': ['point_of_sale', 'account_edi', 'l10n_latam_invoice_document',
                'idtx_pos_report_stock', 'pos_enterprise', 'idtx_pos_sale_idetex'],

    'data': [
        'security/ir.model.access.csv',
        'views/pos_sales_report_views.xml',
        'views/pos_product_sales_report_views.xml',
        'views/menu_existencias.xml',
        'views/order_analysis_customization.xml',
    ],

    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
