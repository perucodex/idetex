{
    'name': 'IDTX Ventas SITPRO (DBF)',
    'version': '1.0',
    'category': 'Sales',
    'summary': 'Estadística de ventas sin IGV desde los DBF de SITPRO '
               '(dp1_estadis / dp1_notacreditod / dp1_estadis_nd)',
    'description': """
Importa las ventas de SITPRO (FoxPro DBF) a un modelo consultable en Odoo:

- Ventas (dp1_estadis + dp1_estadis2), notas de crédito (dp1_notacreditod,
  restan) y notas de débito (dp1_estadis_nd, suman).
- Monto sin IGV; si la moneda es dólares se convierte a soles con el TC del
  documento. Kilos vendidos netos de devoluciones.
- Vendedor resuelto cruzando el pedido (vta_cab_pedido.CDGVEN) con el
  catálogo vta_vendedor.
- Excluye familias de servicio/varios, extornos de NC y facturas a las
  empresas del grupo (clientes cuyo RUC es el de una compañía Odoo).
- Cron incremental: reprocesa solo desde la última sincronización (con una
  ventana de solape para capturar ediciones tardías).
""",
    'author': "Codex Development",
    'website': "https://www.perucodex.com",
    'depends': ['sale'],
    'data': [
        'security/ir.model.access.csv',
        'views/sales_dbf_record_views.xml',
        'data/cron.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
