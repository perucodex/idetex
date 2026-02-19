{
<<<<<<< HEAD
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
=======
    'name': 'IDTX Telas',
    'version': '1.0',
    'summary': 'Gestión de telas y fichas técnicas',
    'description': 'Módulo de ejemplo para registrar y mostrar telas con imágenes y adjuntos.',
    'author': 'Idetex',
    'category': 'Inventory',
    'depends': ['base', 'web','product'],
    'data': [
        'views/tela_views.xml',
        'views/inventory_movement_view.xml',
        'security/ir.model.access.csv',
    ],
    'images': ['static/description/icon.png'],
    'application': True,
>>>>>>> 50a4498bb9d49e8bba2c70c5c801c36b94d2234c
    'license': 'LGPL-3',
}
