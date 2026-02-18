{
    'name': 'Integration Orgatex',
    'version': '1.0',
    'category': 'Tools',
    'license': 'LGPL-3',
    'installable': False,
    'summary': 'Integración de datos con SQL Server',
    'author': 'Tu Nombre',
    'depends': ['base'],
    'data': [
        'views/integration_orgatex_view.xml'
    ],
    'installable': True,
    'external_dependencies': {'python': ['pymssql']},
}
