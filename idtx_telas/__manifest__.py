{
    'name': 'Fabric Management',
    'version': '1.0',
    'category': 'Inventory/Fabric',
    'summary': 'Comprehensive management of fabrics and textiles',
    'description': """
This module allows for the complete management of fabrics (Telas).
It includes a detailed form with technical, commercial, and logistical fields.
    """,
    'author': 'Idetex',
    'depends': ['base', 'mail'],
    'data': [
        'security/ir.model.access.csv',
        'views/fabric_views.xml',
        'demo/fabric_demo.xml',
    ],
    'demo': [
    ],
    'application': True,
    'installable': True,
    'icon': '/idtx_telas/static/description/icon.png',
    'license': 'LGPL-3',
}
