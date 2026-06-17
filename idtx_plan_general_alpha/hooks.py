# -*- coding: utf-8 -*-
import logging

_logger = logging.getLogger(__name__)

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
    ('LISTADORA MAQ 1',         '27', 'BIOTEX',               'Tejeduría',  'TEJEDURIA',  False),
    ('LISTADORA MAQ 2',         '28', 'MAYER',                'Tejeduría',  'TEJEDURIA',  False),
    ('LISTADORA MAQ 3',         '29', 'MAYER',                'Tejeduría',  'TEJEDURIA',  False),
    ('LISTADORA MAQ 4',         '30', 'MAYER',                'Tejeduría',  'TEJEDURIA',  False),
    ('LISTADORA MAQ 5',         '31', 'MAYER',                'Tejeduría',  'TEJEDURIA',  False),
    ('LISTADORA MAQ 6',         '32', 'BIOTEX',               'Tejeduría',  'TEJEDURIA',  False),
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
        try:
            Equipment.create(vals)
            creados += 1
        except Exception:
            _logger.warning('Plan General Alpha: no se pudo crear equipo "%s".', nombre, exc_info=True)

    _logger.info(
        'Plan General Alpha: equipos iniciales — %d creados, %d ya existían.',
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
