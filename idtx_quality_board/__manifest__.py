{
    'name': "Tablero de Calidad",
    'summary': "Accesos Tono Tintorería y Tono Acabado en la app Tableros",
    'description': """
        Agrega en la app Tableros el menú "Calidad" con:
        - Tono Tintorería: solo registros tono=tacho
        - Tono Acabado: solo registros tono=acabado
    """,
    'author': "Codex Development",
    'website': "https://www.perucodex.com",
    'category': 'Uncategorized',
    'version': '19.0.0.5',
    'license': 'LGPL-3',

    'depends': [
        'spreadsheet_dashboard',
        'idtx_quality_control',
    ],

    'data': [
        'views/quality_board_views.xml',
    ],

    'assets': {
        'web.assets_backend': [
            'idtx_quality_board/static/src/quality_board.js',
            'idtx_quality_board/static/src/quality_board.xml',
            'idtx_quality_board/static/src/quality_board.scss',
        ],
    },
}
