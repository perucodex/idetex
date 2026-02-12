{
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
    'license': 'LGPL-3',
}
