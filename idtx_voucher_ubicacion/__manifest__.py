# -*- coding: utf-8 -*-
{
    'name': "Ubicación de piezas por talla (TEXPLUS)",
    'summary': "Escribe ALBDET.ALRPIELOC (UBIC) de las piezas de un voucher "
               "según la talla, desde la ficha técnica",
    'description': """
Desde la ficha técnica de un producto RECTO (weave_type='rect'), un botón abre
un wizard donde se ingresa el número completo del voucher (hoja de ruta), p. ej.
3319242 (el último dígito es el BarCodReo). Lee las piezas del voucher en TEXPLUS
(BARPIE), toma la talla del prefijo del código de pieza (antes del "-"), la cruza
con la pestaña Tallas de la ficha y escribe "largo/ancho" en ALBDET.ALRPIELOC de
cada pieza. Respeta el flag texplus_write_enabled (en modo lectura solo simula).
    """,
    'author': "Codex Development",
    'website': "https://www.perucodex.com",
    'category': 'Manufacturing',
    'version': '19.0.0.0',
    'license': 'LGPL-3',
    'depends': [
        'idtx_product_development',
        'idtx_mrp',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/voucher_ubicacion_wizard_views.xml',
        'views/technical_sheet_views.xml',
    ],
}
