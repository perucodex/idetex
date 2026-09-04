{
    'name': "Control de Calidad de Partidas (Odoo)",

    'summary': "Evaluaciones de calidad sobre las partidas de producción de idtx_mrp",

    'description': """
Control de calidad de partidas de producción (mrp.workorder.batch).

Port de idtx_batch_quality (que trabaja sobre las partidas TEXPLUS de
idtx_batch_control) a las partidas nativas de Odoo de idtx_mrp:

* Evaluación de tono (tacho / secado / acabado) desde tablet y desde la partida.
* Auditoría de apariencia por rollo con catálogo de defectos por área.
* Estabilidad dimensional / revirado y solidez del color al lavado (laboratorio).
* Recepción de muestras con firma, registro de laboratorio e informe resumen
  (PDF, correo y enlace público).

Los datos de cabecera de la partida (cliente, pedido, artículo, color, kilos,
ciclo de reproceso) se derivan de los rollos, sus órdenes de fabricación y el
pedido de venta; ya no se lee TEXPLUS. Convive con idtx_batch_quality: los
modelos usan el prefijo ``qc.``.
    """,

    'author': "Codex Development",
    'website': "https://www.perucodex.com",
    'category': 'Manufacturing/Quality',
    'version': '19.0.1.0.3',
    'license': 'LGPL-3',

    'depends': [
        'web',
        'mail',
        'mrp',
        'sale',
        'quality',
        'quality_control',
        'idtx_mrp',
        'idtx_mrp_shop',
        'idtx_sale_order',
        'idtx_laboratory',
        'idtx_product_development',
    ],

    'data': [
        'security/ir.model.access.csv',
        'data/ir_sequence.xml',
        'data/qc_appearance.xml',
        'data/defectos_acabados.xml',
        'data/defectos_tejeduria.xml',
        'data/defectos_estampado.xml',
        'views/mrp_workorder_batch_views.xml',
        'views/qc_tone_eval_log_views.xml',
        'views/qc_tone_eval_group_views.xml',
        'views/qc_appearance_defect_views.xml',
        'views/qc_dimstab_eval_views.xml',
        'views/qc_sample_reception_views.xml',
        'report/dimrev_report.xml',
        'report/solidez_lavado_report.xml',
        'report/tono_eval_produccion_report.xml',
        'report/batch_lab_summary_report.xml',
        'report/apariencia_eval_report.xml',
        'data/mail_template_data.xml',
        'views/laboratorio_public_templates.xml',
        'views/quality_tone_views.xml',
        'views/quality_defect_views.xml',
        'views/quality_dimrev_views.xml',
        'views/quality_solidez_lavado_views.xml',
        'views/quality_menu.xml',
        'wizards/qc_tone_wizard.xml',
        'wizards/tono_eval_report_wizard.xml',
    ],

    'assets': {
        'web.assets_backend': [
            'idtx_quality_control/static/src/tone_screen/quality_tone_screen.js',
            'idtx_quality_control/static/src/tone_screen/quality_tone_screen.xml',
            'idtx_quality_control/static/src/tone_screen/quality_tone_screen.scss',
            'idtx_quality_control/static/src/defect_screen/quality_defect_screen.js',
            'idtx_quality_control/static/src/defect_screen/quality_defect_screen.xml',
            'idtx_quality_control/static/src/defect_screen/quality_defect_screen.scss',
            'idtx_quality_control/static/src/dimrev_screen/quality_dimrev_screen.js',
            'idtx_quality_control/static/src/dimrev_screen/quality_dimrev_screen.xml',
            'idtx_quality_control/static/src/dimrev_screen/quality_dimrev_screen.scss',
            'idtx_quality_control/static/src/solidez_lavado_screen/quality_solidez_lavado_screen.js',
            'idtx_quality_control/static/src/solidez_lavado_screen/quality_solidez_lavado_screen.xml',
            'idtx_quality_control/static/src/solidez_lavado_screen/quality_solidez_lavado_screen.scss',
            'idtx_quality_control/static/src/sample_reception_screen/quality_sample_reception_screen.js',
            'idtx_quality_control/static/src/sample_reception_screen/quality_sample_reception_screen.xml',
            'idtx_quality_control/static/src/sample_reception_screen/quality_sample_reception_screen.scss',
        ],
    },
    'installable': True,
    'application': False,
}
