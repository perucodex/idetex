{
    'name': "Diagrama ORGATEX",
    'summary': "Diagrama de temperatura del teñido (ORGATEX) en la partida Odoo",
    'description': """
Genera, a partir de los archivos de programa (.prg) y registro (.log) que deja
ORGATEX en su carpeta de histórico, el diagrama de temperatura del teñido de
cada partida y lo guarda en la partida Odoo (mrp.workorder.batch).

El dyelot se localiza con la misma convención que usa idtx_orgatex al enviar
la receta (dígitos de la partida + cantidad de reprocesos) y la conexión a la
base ORGATEX es la de idtx_orgatex (parámetros idtx_orgatex.*).

Parámetro del sistema:
    idtx_diagram_orgatex.shared_path  carpeta HISTORY de ORGATEX montada en el
                                      servidor (por defecto /mnt/sysvol/OT/HISTORY)
    """,
    'author': "Codex Development",
    'website': "https://www.perucodex.com",
    'category': 'Manufacturing',
    'version': '19.0.1.0.0',
    'license': 'LGPL-3',
    'depends': ['idtx_orgatex'],
    'external_dependencies': {'python': ['matplotlib']},
    'data': [
        'security/ir.model.access.csv',
        'data/config_parameters.xml',
        'views/mrp_workorder_batch_views.xml',
    ],
    'installable': True,
    'application': False,
}
