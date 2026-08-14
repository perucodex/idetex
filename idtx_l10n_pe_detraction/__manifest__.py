# -*- coding: utf-8 -*-
{
    'name': 'PE: Tipo de operación 1001 automático (detracción)',
    'summary': 'Marca la factura como Operación Sujeta a Detracción (1001) '
               'cuando lleva productos con código de detracción y supera S/ 700',
    'description': """
El tipo de operación de l10n_pe_edi sale siempre '0101' por defecto y hay que
cambiarlo a mano a '1001' en cada factura con detracción (sin el 1001 el XML
no lleva el bloque de detracción y SUNAT lo observa).

Este módulo lo calcula solo:
- Si alguna línea tiene un producto con código de detracción (y % > 0) y el
  total supera S/ 700 (convertido a PEN si la factura está en otra moneda),
  el tipo de operación pasa a '1001'.
- Si el usuario eligió a mano otro tipo distinto de 0101/1001 (p.ej. 0200
  exportación), se respeta y NO se pisa al editar líneas.
- Solo aplica a facturas de venta (no NC/ND).
    """,
    'author': "Codex Development",
    'website': "https://www.perucodex.com",
    'category': 'Accounting/Localizations',
    'version': '19.0.1.2.0',
    'license': 'LGPL-3',
    'depends': ['l10n_pe_edi'],
    'data': [
        'views/account_move_views.xml',
        'data/mail_template_data.xml',
        'data/account_journal_data.xml',
        'data/selection_labels_data.xml',
    ],
    'installable': True,
}
