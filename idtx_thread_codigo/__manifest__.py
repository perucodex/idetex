# -*- coding: utf-8 -*-
{
    'name': 'Hilado - Maestro de Código',
    'summary': 'Crea productos de hilado (is_thread) con sus atributos y genera el '
               'código, replicando el formulario VFP codigohilocrud.',
    'description': """
Replica el "Maestro de Codigo Hilos" (Visual FoxPro, tabla codigohilocrud) dentro
de product.template para los productos is_thread:

- Atributos por catálogo (Many2one): Título, Cabos, Proceso, Composición, Línea,
  Diseño (reutiliza product.title / product.fiber / product.family y agrega los
  catálogos faltantes Cabos, Proceso, Línea, Diseño).
- Campos Familia / Color / Detalle color / Cliente (IDETEX/WTS/OTROS) y Desarrollo.
- Botón "Generar código": arma default_code = título+cabos+proceso+línea+
  composición+diseño (concatenación de los códigos), como el GENERAR del VFP, y
  una descripción sugerida (editable).
- Todo en la pestaña existente "Datos de Hilado" (visible solo si is_thread).
""",
    'author': 'IDETEX',
    'category': 'Producción Textil',
    'version': '19.0.1.3.0',
    'license': 'LGPL-3',
    'depends': ['idtx_product_development', 'mail'],
    # 'post_init_hook': 'post_init_hook',
    'data': [
        'security/thread_groups.xml',
        'security/ir.model.access.csv',
        'views/thread_catalog_views.xml',
        'views/thread_code_views.xml',
        'views/product_template_views.xml',
        'views/report_technical_sheet_weaving.xml',
    ],
    'installable': True,
    'application': False,
}
