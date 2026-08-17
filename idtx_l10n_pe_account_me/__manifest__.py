# -*- coding: utf-8 -*-
{
    'name': 'PE: Cuentas por cobrar/pagar en moneda extranjera (MN/ME)',
    'summary': 'Divisionarias 12/42 separadas por moneda: la factura usa la '
               'cuenta ME cuando su moneda es distinta a la de la compañía',
    'description': """
La contabilidad peruana acostumbra divisionarias separadas para documentos en
moneda nacional y extranjera (p.ej. 12121 MN / 12122 ME, 42121 / 42122).
Odoo estándar usa una sola cuenta por cobrar/pagar por cliente, sin mirar la
moneda de la factura.

Este módulo agrega:

- Dos campos por compañía en el cliente/proveedor: "Cuenta por cobrar (ME)" y
  "Cuenta por pagar (ME)", con la misma mecánica de herencia que los campos
  estándar (default por compañía vía ir.default, valor explícito solo si se
  asigna en la ficha).
- Los defaults se configuran en Ajustes > Contabilidad > bloque "Cuentas por
  moneda extranjera (ME)" (hacen ir.default.set por compañía al guardar).
- Al generar el asiento de una factura cuya moneda no es la de la compañía,
  la línea por cobrar/pagar usa la cuenta ME, respetando el mapeo de la
  posición fiscal. Sin cuenta ME configurada se comporta igual que Odoo
  estándar (nunca deja la línea sin cuenta).

Nota: las divisionarias ME (p.ej. 12122 y 42122) no existen en el plan de
l10n_pe (solo llega a 4 dígitos); hay que crearlas en el plan de cuentas con
tipo "Por cobrar" / "Por pagar" antes de configurar los defaults.
    """,
    'author': "Codex Development",
    'website': "https://www.perucodex.com",
    'category': 'Accounting/Localizations',
    'version': '19.0.1.3.0',
    'license': 'LGPL-3',
    'depends': ['account'],
    'data': [
        'views/res_partner_views.xml',
        'views/res_config_settings_views.xml',
        'views/account_move_views.xml',
    ],
    'installable': True,
}
