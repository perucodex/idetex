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
        'data/ir_sequence.xml',
        'data/control_apariencia.xml',
        'data/defectos_acabados.xml',
        'data/defectos_tejeduria.xml',

        'views/control_pedido_line_views.xml',
        'views/control_tono_eval_log_views.xml',
        'views/control_tono_eval_group_views.xml',
        'views/control_apariencia_defecto_views.xml',
        'views/control_estabilidad_revirado_eval_views.xml',
        'report/dimrev_report.xml',
        'report/solidez_lavado_report.xml',
        'views/quality_tone_screen.xml',
        'views/quality_defect_screen.xml',
        'views/quality_dimrev_screen.xml',
        'views/quality_solidez_lavado_screen.xml',

        'wizards/control_tono_wizard.xml',

    ],

    'assets': {
        'web.assets_backend': [
            'idtx_batch_quality/static/src/list_renderer_escape_guard.js',
            'idtx_batch_quality/static/src/tone_screen/quality_tone_screen.js',
            'idtx_batch_quality/static/src/tone_screen/quality_tone_screen.xml',
            'idtx_batch_quality/static/src/tone_screen/quality_tone_screen.scss',
            'idtx_batch_quality/static/src/defect_screen/quality_defect_screen.js',
            'idtx_batch_quality/static/src/defect_screen/quality_defect_screen.xml',
            'idtx_batch_quality/static/src/defect_screen/quality_defect_screen.scss',
            'idtx_batch_quality/static/src/dimrev_screen/quality_dimrev_screen.js',
            'idtx_batch_quality/static/src/dimrev_screen/quality_dimrev_screen.xml',
            'idtx_batch_quality/static/src/dimrev_screen/quality_dimrev_screen.scss',
            'idtx_batch_quality/static/src/solidez_lavado_screen/quality_solidez_lavado_screen.js',
            'idtx_batch_quality/static/src/solidez_lavado_screen/quality_solidez_lavado_screen.xml',
            'idtx_batch_quality/static/src/solidez_lavado_screen/quality_solidez_lavado_screen.scss',
        ],
    },
} 