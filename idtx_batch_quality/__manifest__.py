{
    'name': "Control de Calidad Tonos",

    'summary': "Short (1 phrase/line) summary of the module's purpose",

    'description': 
    """
        Modulo de Calidad para el control de tonos en los pedidos de tintas.
        Permite evaluar los tonos de cada linea del pedido y registrar las evaluaciones realizadas.
    """,

    'author': "Joe Miranda",
    'website': "https://gestionidtx.com",
    'category': 'Uncategorized',
    'version': '0.1',
    'license': 'LGPL-3',

    'depends': ['base', "web", "mrp", "idtx_batch_control", 'quality_control'],

    'data': [
        'security/ir.model.access.csv',

        'views/control_pedido_line_views.xml',
        'views/control_tono_eval_log_views.xml',
        'views/control_apariencia_defecto_views.xml',
        'views/quality_defect_screen.xml',

        'wizards/control_tono_wizard.xml',

    ],

    'assets': {
        'web.assets_backend': [
            'idtx_batch_quality/static/src/defect_screen/quality_defect_screen.js',
            'idtx_batch_quality/static/src/defect_screen/quality_defect_screen.xml',
            'idtx_batch_quality/static/src/defect_screen/quality_defect_screen.scss',
        ],
    },
} 