{
    'name': "Control de Calidad Partidas",

    'summary': "Control de Calidad y Evaluaciones de Partidas",

    'description': 
    """
        Modulo de Calidad para el control de partidas.
        Permite evaluar las partidas de cada linea del pedido y registrar las evaluaciones realizadas.
    """,

    'author': "Jean Paul Casis",
    'website': "https://www.perucodex.com",
    'category': 'Uncategorized',
    'version': '0.1',
    'license': 'LGPL-3',

    'depends': ['base', "web", "mrp", "mail", "idtx_batch_control", 'quality', 'quality_control', 'idtx_product_development'],

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
        'report/pedido_line_laboratorio_summary_report.xml',
        'report/apariencia_eval_report.xml',
        'data/mail_template_data.xml',
        'views/laboratorio_public_templates.xml',
        'views/quality_tone_views.xml',
        'views/quality_defect_views.xml',
        'views/quality_dimrev_views.xml',
        'views/quality_solidez_lavado_views.xml',
        'views/quality_menu.xml',

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