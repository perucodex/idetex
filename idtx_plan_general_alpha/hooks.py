# -*- coding: utf-8 -*-
import logging

_logger = logging.getLogger(__name__)

# Layout físico del piso TEJEDURIA — (serial_no, slot_index)
# Patrón serpiente 24 columnas, distribución real de fábrica.
_TEJEDURIA_FLOOR_LAYOUT = [
    # FILA 0: MAQ 1,2,3 | MAQ 11,12 | MAQ 58,59,64,65,70,71,76,77,82,83,88
    ('TEJ1',  0), ('TEJ2',  1), ('TEJ3',  2),
    ('TEJ11', 6), ('TEJ12', 7),
    ('TEJ58', 13), ('TEJ59', 14), ('TEJ64', 15), ('TEJ65', 16),
    ('TEJ70', 17), ('TEJ71', 18), ('TEJ76', 19), ('TEJ77', 20),
    ('TEJ82', 21), ('TEJ83', 22), ('TEJ88', 23),
    # FILA 1 (serpiente): MAQ 6,5,4 | MAQ 14,15,16,17 | MAQ 57,60,63,66,69,72,75,78,81,84,87
    ('TEJ6',  24), ('TEJ5',  25), ('TEJ4',  26),
    ('TEJ14', 30), ('TEJ15', 31), ('TEJ16', 33), ('TEJ17', 34),
    ('TEJ57', 37), ('TEJ60', 38), ('TEJ63', 39), ('TEJ66', 40),
    ('TEJ69', 41), ('TEJ72', 42), ('TEJ75', 43), ('TEJ78', 44),
    ('TEJ81', 45), ('TEJ84', 46), ('TEJ87', 47),
    # FILA 2: MAQ 7,8,9 | MAQ 21,20,19,18 (inv) | MAQ 56,61,62,67,68,73,74,79,80,85,86
    ('TEJ7',  48), ('TEJ8',  49), ('TEJ9',  50),
    ('TEJ21', 54), ('TEJ20', 55), ('TEJ19', 57), ('TEJ18', 58),
    ('TEJ56', 61), ('TEJ61', 62), ('TEJ62', 63), ('TEJ67', 64),
    ('TEJ68', 65), ('TEJ73', 66), ('TEJ74', 67), ('TEJ79', 68),
    ('TEJ80', 69), ('TEJ85', 70), ('TEJ86', 71),
    # FILA 3: MAQ 10 | MAQ 22,23,24,25
    ('TEJ10', 72),
    ('TEJ22', 78), ('TEJ23', 79), ('TEJ24', 81), ('TEJ25', 82),
    # FILA 4: MAQ 26 sola
    ('TEJ26', 97),
    # FILA 5: MAQ 27,28,29,30 | MAQ 31,32
    ('TEJ27', 123), ('TEJ28', 124), ('TEJ29', 125), ('TEJ30', 126),
    ('TEJ31', 128), ('TEJ32', 129),
    # FILA 6 (serpiente): MAQ 38,37,36,35 | MAQ 34,33
    ('TEJ38', 147), ('TEJ37', 148), ('TEJ36', 149), ('TEJ35', 150),
    ('TEJ34', 152), ('TEJ33', 153),
    # FILA 7: MAQ 39,40,41,42 | MAQ 43,44
    ('TEJ39', 171), ('TEJ40', 172), ('TEJ41', 173), ('TEJ42', 174),
    ('TEJ43', 176), ('TEJ44', 177),
    # FILA 8 (serpiente): MAQ 50,49,48,47 | MAQ 46,45
    ('TEJ50', 195), ('TEJ49', 196), ('TEJ48', 197), ('TEJ47', 198),
    ('TEJ46', 200), ('TEJ45', 201),
    # FILA 9: MAQ 51,52,53,54 | MAQ 55
    ('TEJ51', 219), ('TEJ52', 220), ('TEJ53', 221), ('TEJ54', 222),
    ('TEJ55', 224),
]

# (nombre, serial_no, modelo, departamento, centro_trabajo, habilitado)
_EQUIPOS_INICIALES = [
    ('MAQ 38',                  '1',  'BRAZZOLI',             'Tintorería', 'TINTORERIA', True),
    ('MAQ 32',                  '2',  'MCS',                  'Tintorería', 'TINTORERIA', False),
    ('MAQ 35',                  '3',  'BRAZZOLI',             'Tintorería', 'TINTORERIA', False),
    ('MAQ 29',                  '4',  'MCS',                  'Tintorería', 'TINTORERIA', False),
    ('MAQ 34',                  '5',  'BRAZZOLI',             'Tintorería', 'TINTORERIA', False),
    ('MAQ 35',                  '6',  'BRAZZOLI',             'Tintorería', 'TINTORERIA', False),
    ('MAQ 37',                  '7',  'BRAZZOLI',             'Tintorería', 'TINTORERIA', False),
    ('MAQ 20',                  '8',  'MCS',                  'Tintorería', 'TINTORERIA', False),
    ('MAQ 12',                  '9',  'MCS',                  'Tintorería', 'TINTORERIA', False),
    ('MAQ 11',                  '10', 'MCS',                  'Tintorería', 'TINTORERIA', False),
    ('MAQ 10',                  '11', 'MCS',                  'Tintorería', 'TINTORERIA', False),
    ('MAQ 9',                   '12', 'DANITECH',             'Tintorería', 'TINTORERIA', False),
    ('MAQ 8',                   '13', 'DANITECH',             'Tintorería', 'TINTORERIA', False),
    ('MAQ 7',                   '14', 'BRAZZOLI',             'Tintorería', 'TINTORERIA', False),
    ('MAQ 1',                   '15', 'THIES',                'Tintorería', 'TINTORERIA', False),
    ('MAQ 2',                   '16', 'THIES',                'Tintorería', 'TINTORERIA', False),
    ('MAQ 3',                   '17', 'THIES',                'Tintorería', 'TINTORERIA', False),
    ('MAQ 4',                   '18', 'THIES',                'Tintorería', 'TINTORERIA', False),
    ('MAQ 5',                   '19', 'THIES',                'Tintorería', 'TINTORERIA', False),
    ('MAQ 6',                   '20', 'FONG',                 'Tintorería', 'TINTORERIA', False),
    ('MAQ TERMOFIJADO MESDAN',  '21', 'TERMOFIJADO MESDAN',   'Tintorería', 'TINTORERIA', False),
    ('BIANCALANI',              '22', 'BIANCALANI',           'Tintorería', 'TINTORERIA', False),
    ('ABRIDORA N °1',           '23', 'ABRIDORA',             'Tintorería', 'TINTORERIA', False),
    ('ABRIDORA N °2',           '24', 'ABRIDORA',             'Tintorería', 'TINTORERIA', False),
    ('HIDROEXTRACTORA CORINO',  '25', 'HIDROEXTRACTORA CORINO',  'Tintorería', 'TINTORERIA', False),
    ('HIDROEXTRACTORA BIANCO',  '26', 'HIDROEXTRACTORA BIANCO',  'Tintorería', 'TINTORERIA', False),
    ('LISTADORA MAQ 1',         'TEJ1',     'BIOTEX',    'Tejeduría', 'TEJEDURIA', False),
    ('LISTADORA MAQ 2',         'TEJ2',     'MAYER',     'Tejeduría', 'TEJEDURIA', False),
    ('LISTADORA MAQ 3',         'TEJ3',     'MAYER',     'Tejeduría', 'TEJEDURIA', False),
    ('LISTADORA MAQ 4',         'TEJ4',     'MAYER',     'Tejeduría', 'TEJEDURIA', False),
    ('LISTADORA MAQ 5',         'TEJ5',     'MAYER',     'Tejeduría', 'TEJEDURIA', False),
    ('LISTADORA MAQ 6',         'TEJ6',     'BIOTEX',    'Tejeduría', 'TEJEDURIA', False),
    ('LISTADORA MAQ 7',         'TEJ7',   'MAYER',     'Tejeduría', 'TEJEDURIA', False),
    ('LISTADORA MAQ 8',         'TEJ8',   'MAYER',     'Tejeduría', 'TEJEDURIA', False),
    ('LISTADORA MAQ 9',         'TEJ9',   'MAYER',     'Tejeduría', 'TEJEDURIA', False),
    ('JERSERA MAQ 10',          'TEJ10',  'SANYONG',   'Tejeduría', 'TEJEDURIA', False),
    ('JERSERA MAQ 11',          'TEJ11',  'BIOTEX',    'Tejeduría', 'TEJEDURIA', False),
    ('GAMUZA MAQ 12',           'TEJ12',  'BIOTEX',    'Tejeduría', 'TEJEDURIA', False),
    ('JERSERA MAQ 14',          'TEJ14',  'BIOTEX',    'Tejeduría', 'TEJEDURIA', False),
    ('JERSERA MAQ 15',          'TEJ15',  'BIOTEX',    'Tejeduría', 'TEJEDURIA', False),
    ('GAMUZA MAQ 16',           'TEJ16',  'BIOTEX',    'Tejeduría', 'TEJEDURIA', False),
    ('JERSERA MAQ 17',          'TEJ17',  'MAYER',     'Tejeduría', 'TEJEDURIA', False),
    ('JERSERA MAQ 18',          'TEJ18',  'MAYER',     'Tejeduría', 'TEJEDURIA', False),
    ('RIPERA MAQ 19',           'TEJ19',  'BIOTEX',    'Tejeduría', 'TEJEDURIA', False),
    ('GAMUZA MAQ 20',           'TEJ20',  'BIOTEX',    'Tejeduría', 'TEJEDURIA', False),
    ('GAMUZA MAQ 21',           'TEJ21',  'BIOTEX',    'Tejeduría', 'TEJEDURIA', False),
    ('RIPERA MAQ 22',           'TEJ22',  'BIOTEX',    'Tejeduría', 'TEJEDURIA', False),
    ('RIPERA MAQ 23',           'TEJ23',  'BIOTEX',    'Tejeduría', 'TEJEDURIA', False),
    ('RIPERA MAQ 24',           'TEJ24',  'BIOTEX',    'Tejeduría', 'TEJEDURIA', False),
    ('JERSERA MAQ 25',          'TEJ25',  'MAYER',     'Tejeduría', 'TEJEDURIA', False),
    ('RIPERA MAQ 26',           'TEJ26',  'ORIZIO',    'Tejeduría', 'TEJEDURIA', False),
    ('JERSERA MAQ 27',          'TEJ27',  'MAYER',     'Tejeduría', 'TEJEDURIA', False),
    ('JERSERA MAQ 28',          'TEJ28',  'MAYER',     'Tejeduría', 'TEJEDURIA', False),
    ('JERSERA MAQ 29',          'TEJ29',  'MAYER',     'Tejeduría', 'TEJEDURIA', False),
    ('JERSERA MAQ 30',          'TEJ30',  'MAYER',     'Tejeduría', 'TEJEDURIA', False),
    ('JERSERA MAQ 31',          'TEJ31',  'MAYER',     'Tejeduría', 'TEJEDURIA', False),
    ('JERSERA MAQ 32',          'TEJ32',  'MAYER',     'Tejeduría', 'TEJEDURIA', False),
    ('JERSERA MAQ 33',          'TEJ33',  'MAYER',     'Tejeduría', 'TEJEDURIA', False),
    ('JERSERA MAQ 34',          'TEJ34',  'MAYER',     'Tejeduría', 'TEJEDURIA', False),
    ('JERSERA MAQ 35',          'TEJ35',  'MAYER',     'Tejeduría', 'TEJEDURIA', False),
    ('JERSERA MAQ 36',          'TEJ36',  'MAYER',     'Tejeduría', 'TEJEDURIA', False),
    ('JERSERA MAQ 37',          'TEJ37',  'MAYER',     'Tejeduría', 'TEJEDURIA', False),
    ('JERSERA MAQ 38',          'TEJ38',  'MAYER',     'Tejeduría', 'TEJEDURIA', False),
    ('JERSERA MAQ 39',          'TEJ39',  'MAYER',     'Tejeduría', 'TEJEDURIA', False),
    ('JERSERA MAQ 40',          'TEJ40',  'MAYER',     'Tejeduría', 'TEJEDURIA', False),
    ('JERSERA MAQ 41',          'TEJ41',  'MAYER',     'Tejeduría', 'TEJEDURIA', False),
    ('JERSERA MAQ 42',          'TEJ42',  'MAYER',     'Tejeduría', 'TEJEDURIA', False),
    ('JERSERA MAQ 43',          'TEJ43',  'MAYER',     'Tejeduría', 'TEJEDURIA', False),
    ('JERSERA MAQ 44',          'TEJ44',  'MAYER',     'Tejeduría', 'TEJEDURIA', False),
    ('JERSERA MAQ 45',          'TEJ45',  'MAYER',     'Tejeduría', 'TEJEDURIA', False),
    ('JERSERA MAQ 46',          'TEJ46',  'MAYER',     'Tejeduría', 'TEJEDURIA', False),
    ('JERSERA MAQ 47',          'TEJ47',  'MAYER',     'Tejeduría', 'TEJEDURIA', False),
    ('JERSERA MAQ 48',          'TEJ48',  'HAVERTEX',  'Tejeduría', 'TEJEDURIA', False),
    ('JERSERA MAQ 49',          'TEJ49',  'HAVERTEX',  'Tejeduría', 'TEJEDURIA', False),
    ('JERSERA MAQ 50',          'TEJ50',  'ORIZIO',    'Tejeduría', 'TEJEDURIA', False),
    ('GAMUZA MAQ 51',           'TEJ51',  'BIOTEX',    'Tejeduría', 'TEJEDURIA', False),
    ('GAMUZA MAQ 52',           'TEJ52',  'BIOTEX',    'Tejeduría', 'TEJEDURIA', False),
    ('RIPERA MAQ 53',           'TEJ53',  'BIOTEX',    'Tejeduría', 'TEJEDURIA', False),
    ('RIPERA MAQ 54',           'TEJ54',  'BIOTEX',    'Tejeduría', 'TEJEDURIA', False),
    ('JERSERA MAQ 55',          'TEJ55',  'BECK',      'Tejeduría', 'TEJEDURIA', False),
    ('RIPERA MAQ 56',           'TEJ56',  'MAYER',     'Tejeduría', 'TEJEDURIA', False),
    ('GAMUZA MAQ 57',           'TEJ57',  'MAYER',     'Tejeduría', 'TEJEDURIA', False),
    ('GAMUZA MAQ 58',           'TEJ58',  'MAYER',     'Tejeduría', 'TEJEDURIA', False),
    ('RIPERA MAQ 59',           'TEJ59',  'ORIZIO',    'Tejeduría', 'TEJEDURIA', False),
    ('RIPERA MAQ 60',           'TEJ60',  'MAYER',     'Tejeduría', 'TEJEDURIA', False),
    ('RIPERA MAQ 61',           'TEJ61',  'MAYER',     'Tejeduría', 'TEJEDURIA', False),
    ('RIPERA MAQ 62',           'TEJ62',  'MAYER',     'Tejeduría', 'TEJEDURIA', False),
    ('RIPERA MAQ 63',           'TEJ63',  'MAYER',     'Tejeduría', 'TEJEDURIA', False),
    ('RIPERA MAQ 64',           'TEJ64',  'ORIZIO',    'Tejeduría', 'TEJEDURIA', False),
    ('RIPERA MAQ 65',           'TEJ65',  'ORIZIO',    'Tejeduría', 'TEJEDURIA', False),
    ('RIPERA MAQ 66',           'TEJ66',  'MAYER',     'Tejeduría', 'TEJEDURIA', False),
    ('RIPERA MAQ 67',           'TEJ67',  'MAYER',     'Tejeduría', 'TEJEDURIA', False),
    ('RIPERA MAQ 68',           'TEJ68',  'MAYER',     'Tejeduría', 'TEJEDURIA', False),
    ('JERSERA MAQ 69',          'TEJ69',  'MAYER',     'Tejeduría', 'TEJEDURIA', False),
    ('JERSERA MAQ 70',          'TEJ70',  'BECK',      'Tejeduría', 'TEJEDURIA', False),
    ('FELPA MAQ 71',            'TEJ71',  'BECK',      'Tejeduría', 'TEJEDURIA', False),
    ('JERSERA MAQ 72',          'TEJ72',  'MAYER',     'Tejeduría', 'TEJEDURIA', False),
    ('RIPERA MAQ 73',           'TEJ73',  'ORIZIO',    'Tejeduría', 'TEJEDURIA', False),
    ('RIPERA MAQ 74',           'TEJ74',  'ORIZIO',    'Tejeduría', 'TEJEDURIA', False),
    ('JERSERA MAQ 75',          'TEJ75',  'MAYER',     'Tejeduría', 'TEJEDURIA', False),
    ('FRANELA 3 HILOS MAQ 76',  'TEJ76',  'ORIZIO',    'Tejeduría', 'TEJEDURIA', False),
    ('JERSERA MAQ 77',          'TEJ77',  'ORIZIO',    'Tejeduría', 'TEJEDURIA', False),
    ('RIPERA MAQ 78',           'TEJ78',  'ORIZIO',    'Tejeduría', 'TEJEDURIA', False),
    ('RIPERA MAQ 79',           'TEJ79',  'ORIZIO',    'Tejeduría', 'TEJEDURIA', False),
    ('RIPERA MAQ 80',           'TEJ80',  'ORIZIO',    'Tejeduría', 'TEJEDURIA', False),
    ('RIPERA MAQ 81',           'TEJ81',  'ORIZIO',    'Tejeduría', 'TEJEDURIA', False),
    ('JERSERA MAQ 82',          'TEJ82',  'ORIZIO',    'Tejeduría', 'TEJEDURIA', False),
    ('JERSERA MAQ 83',          'TEJ83',  'ORIZIO',    'Tejeduría', 'TEJEDURIA', False),
    ('RIPERA MAQ 84',           'TEJ84',  'ORIZIO',    'Tejeduría', 'TEJEDURIA', False),
    ('RIPERA MAQ 85',           'TEJ85',  'ORIZIO',    'Tejeduría', 'TEJEDURIA', False),
    ('RIPERA MAQ 86',           'TEJ86',  'SANTEX',    'Tejeduría', 'TEJEDURIA', False),
    ('RIPERA MAQ 87',           'TEJ87',  'MAYER',     'Tejeduría', 'TEJEDURIA', False),
    ('GAMUZA MAQ 88',           'TEJ88',  'ORIZIO',    'Tejeduría', 'TEJEDURIA', False),
]


def _get_or_create_department(env, nombre):
    company = env.company
    dept = env['hr.department'].search([
        ('name', '=', nombre),
        ('company_id', '=', company.id),
    ], limit=1)
    if not dept:
        dept = env['hr.department'].create({
            'name': nombre,
            'company_id': company.id,
        })
        _logger.info('Plan General Alpha: departamento HR creado: %s', nombre)
    return dept


def _get_or_create_workcenter(env, nombre):
    company = env.company
    wc = env['mrp.workcenter'].search([
        ('name', '=', nombre),
        ('company_id', '=', company.id),
    ], limit=1)
    if not wc:
        wc = env['mrp.workcenter'].create({
            'name': nombre,
            'company_id': company.id,
        })
        _logger.info('Plan General Alpha: centro de trabajo creado: %s', nombre)
    return wc


def _create_initial_equipment(env):
    """Crea los equipos/máquinas iniciales si aún no existen."""
    Equipment = env['maintenance.equipment']
    fields_eq = Equipment._fields
    tiene_department = 'department_id' in fields_eq
    tiene_workcenter = 'workcenter_id' in fields_eq
    tiene_idtx = 'enabled' in fields_eq

    depts = {}
    if tiene_department:
        try:
            for nombre_dept in ('Tintorería', 'Tejeduría'):
                depts[nombre_dept] = _get_or_create_department(env, nombre_dept)
        except Exception:
            _logger.warning('Plan General Alpha: no se pudieron crear departamentos HR.', exc_info=True)
            tiene_department = False

    workcenters = {}
    if tiene_workcenter:
        try:
            for nombre_wc in ('TINTORERIA', 'TEJEDURIA'):
                workcenters[nombre_wc] = _get_or_create_workcenter(env, nombre_wc)
        except Exception:
            _logger.warning('Plan General Alpha: no se pudieron crear centros de trabajo.', exc_info=True)
            tiene_workcenter = False

    tiene_machine_state = 'machine_state' in fields_eq

    creados = omitidos = 0
    for nombre, serial_no, modelo, dept_nombre, wc_nombre, habilitado in _EQUIPOS_INICIALES:
        if Equipment.search([('serial_no', '=', serial_no)], limit=1):
            omitidos += 1
            continue
        vals = {
            'name': nombre,
            'serial_no': serial_no,
            'model': modelo,
            'company_id': env.company.id,
        }
        if tiene_department and dept_nombre in depts:
            vals['department_id'] = depts[dept_nombre].id
            vals['equipment_assign_to'] = 'department'
        if tiene_workcenter and wc_nombre in workcenters:
            vals['workcenter_id'] = workcenters[wc_nombre].id
        if tiene_idtx:
            vals['enabled'] = habilitado
            vals['oos'] = False
        if tiene_machine_state:
            vals['machine_state'] = 'operativa' if habilitado else 'apagada'
        try:
            Equipment.create(vals)
            creados += 1
        except Exception:
            _logger.warning('Plan General Alpha: no se pudo crear equipo "%s".', nombre, exc_info=True)

    _logger.info(
        'Plan General Alpha: equipos iniciales — %d creados, %d ya existían.',
        creados, omitidos,
    )


def _create_floor_layouts(env):
    """Crea el layout físico del piso TEJEDURIA al instalar el módulo."""
    if 'idtx.alpha.floor.layout' not in env.registry.models:
        _logger.warning('Plan General Alpha: modelo idtx.alpha.floor.layout no disponible.')
        return
    Layout = env['idtx.alpha.floor.layout']
    Equipment = env['maintenance.equipment']

    creados = omitidos = 0
    for serial_no, slot_index in _TEJEDURIA_FLOOR_LAYOUT:
        eq = Equipment.search([('serial_no', '=', serial_no)], limit=1)
        if not eq:
            _logger.debug('Plan General Alpha: equipo %s no encontrado, omitiendo layout.', serial_no)
            continue
        existing = Layout.search([
            ('equipment_id', '=', eq.id),
            ('workcenter', '=', 'TEJEDURIA'),
        ], limit=1)
        if existing:
            omitidos += 1
            continue
        try:
            Layout.create({
                'equipment_id': eq.id,
                'workcenter': 'TEJEDURIA',
                'slot_index': slot_index,
            })
            creados += 1
        except Exception:
            _logger.warning(
                'Plan General Alpha: no se pudo crear layout para %s.', serial_no, exc_info=True
            )

    _logger.info(
        'Plan General Alpha: floor layout TEJEDURIA — %d creados, %d ya existían.',
        creados, omitidos,
    )


def post_init_hook(env):
    """Configura el dashboard y crea los equipos/máquinas iniciales."""
    try:
        estados_id = env.ref('idtx_plan_general_alpha.action_plan_alpha_dash_estados').id
        clientes_id = env.ref('idtx_plan_general_alpha.action_plan_alpha_dash_clientes').id
        area_id    = env.ref('idtx_plan_general_alpha.action_plan_alpha_dash_area').id
        proceso_id = env.ref('idtx_plan_general_alpha.action_plan_alpha_dash_proceso').id

        arch = (
            '<form string="Dashboard de Planeamiento">'
            '<board style="1-1">'
            '<column>'
            f'<action name="{estados_id}" string="Estados de Pedidos" view_mode="graph"/>'
            f'<action name="{area_id}" string="Partidas por Area (kg)" view_mode="graph"/>'
            '</column>'
            '<column>'
            f'<action name="{clientes_id}" string="Top Clientes (kg)" view_mode="graph"/>'
            f'<action name="{proceso_id}" string="Partidas por Proceso" view_mode="graph"/>'
            '</column>'
            '</board>'
            '</form>'
        )

        board_view = env.ref('idtx_plan_general_alpha.view_plan_alpha_dashboard_board')
        board_view.with_context(no_cow=True).write({'arch': arch})
        _logger.info('Plan General Alpha: dashboard board configurado correctamente.')
    except Exception:
        _logger.exception('Plan General Alpha: error al configurar el dashboard board.')

    _create_initial_equipment(env)
    _create_floor_layouts(env)
