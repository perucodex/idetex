# -*- coding: utf-8 -*-
import logging
import re
import unicodedata

_logger = logging.getLogger(__name__)

_MODULE = 'idtx_plan_general_alpha'


def _slug(text):
    """Normaliza un nombre a un sufijo de xml_id seguro (sin tildes/Ñ/espacios)."""
    norm = unicodedata.normalize('NFKD', text or '').encode('ascii', 'ignore').decode('ascii')
    return re.sub(r'[^a-zA-Z0-9]+', '_', norm).strip('_').lower()


def _track_owned(env, model, res_id, xml_id):
    """Marca un registro como propiedad de este módulo en ir.model.data,
    para que al DESINSTALARLO Odoo lo elimine automáticamente (o falle
    silenciosamente ese registro puntual si algo más lo referencia — Odoo
    nunca aborta el uninstall completo por eso).
    Se llama tanto si el registro se acaba de crear como si ya existía,
    porque el nombre/serial buscado (departamentos Tintorería/Tejeduría,
    equipos por serial_no de _EQUIPOS_INICIALES) es específico de este
    módulo — pero SIEMPRE filtrado por la compañía actual, así que nunca
    reclama datos de otra compañía."""
    IMD = env['ir.model.data'].sudo()
    if IMD.search_count([('module', '=', _MODULE), ('name', '=', xml_id)]):
        return
    IMD.create({
        'module': _MODULE,
        'name': xml_id,
        'model': model,
        'res_id': res_id,
        'noupdate': True,
    })

_TEJEDURIA_FLOOR_LAYOUT = [
    ('TEJ1',  0),   ('TEJ2',  3),  ('TEJ3',  4),
    ('TEJ11', 5),   ('TEJ12', 6),
    ('TEJ58', 13),  ('TEJ59', 14), ('TEJ64', 15), ('TEJ65', 16),
    ('TEJ70', 17),  ('TEJ71', 18), ('TEJ76', 19), ('TEJ77', 20),
    ('TEJ82', 21),  ('TEJ83', 22), ('TEJ88', 23),
    ('TEJ6',  24),  ('TEJ5',  27), ('TEJ4',  28),
    ('TEJ14', 29),  ('TEJ15', 30), ('TEJ16', 33), ('TEJ17', 34),
    ('TEJ57', 37),  ('TEJ60', 38), ('TEJ63', 39), ('TEJ66', 40),
    ('TEJ69', 41),  ('TEJ72', 42), ('TEJ75', 43), ('TEJ78', 44),
    ('TEJ81', 45),  ('TEJ84', 46), ('TEJ87', 47),
    ('TEJ7',  48),  ('TEJ8',  51), ('TEJ9',  52),
    ('TEJ21', 53),  ('TEJ20', 54), ('TEJ19', 57), ('TEJ18', 58),
    ('TEJ56', 61),  ('TEJ61', 62), ('TEJ62', 63), ('TEJ67', 64),
    ('TEJ68', 65),  ('TEJ73', 66), ('TEJ74', 67), ('TEJ79', 68),
    ('TEJ80', 69),  ('TEJ85', 70), ('TEJ86', 71),
    ('TEJ10', 72),
    ('TEJ22', 77),  ('TEJ23', 78), ('TEJ24', 81), ('TEJ25', 82),
    ('TEJ26', 96),
    ('TEJ27', 123), ('TEJ28', 124), ('TEJ29', 125), ('TEJ30', 126),
    ('TEJ31', 129), ('TEJ32', 130),
    ('TEJ38', 147), ('TEJ37', 148), ('TEJ36', 149), ('TEJ35', 150),
    ('TEJ34', 153), ('TEJ33', 154),
    ('TEJ39', 171), ('TEJ40', 172), ('TEJ41', 173), ('TEJ42', 174),
    ('TEJ43', 177), ('TEJ44', 178),
    ('TEJ50', 195), ('TEJ49', 196), ('TEJ48', 197), ('TEJ47', 198),
    ('TEJ46', 201), ('TEJ45', 202),
    ('TEJ51', 219), ('TEJ52', 220), ('TEJ53', 221), ('TEJ54', 222),
    ('TEJ55', 225),
]

# Igual que _TEJEDURIA_FLOOR_LAYOUT pero con celdas combinadas (span_cols,
# span_rows): varias máquinas de TINTORERIA se agrandaron manualmente en la
# cuadrícula (ver ALLOWED_SHAPES / _covered_cells en el controlador). Cada
# tupla es (serial_no, slot_index_ancla, span_cols, span_rows).
_TINTORERIA_FLOOR_LAYOUT = [
    ('TEÑ21', 0, 1, 2),   ('TEÑ20', 2, 1, 2),   ('TEÑ22', 4, 1, 2),
    ('TEÑ19', 30, 1, 2),  ('TEÑ18', 32, 1, 2),  ('TEÑ17', 34, 1, 2),
    ('TEÑ16', 36, 1, 2),  ('TEÑ15', 38, 1, 2),
    ('TEÑ23', 102, 2, 2), ('TEÑ14', 106, 3, 2),
    ('TEÑ13', 111, 1, 2), ('TEÑ12', 113, 1, 2), ('TEÑ11', 115, 1, 2),
    ('TEÑ10', 117, 1, 2), ('TEÑ9',  119, 1, 2),
    ('TEÑ24', 174, 2, 2), ('TEÑ7',  178, 3, 2),
    ('TEÑ6',  182, 1, 2), ('TEÑ5',  184, 1, 2), ('TEÑ8',  187, 2, 2),
    ('TEÑ25', 245, 2, 1), ('TEÑ4',  249, 2, 1), ('TEÑ3',  252, 2, 1),
    ('TEÑ2',  255, 2, 1), ('TEÑ1',  259, 2, 1),
    ('TEÑ26', 293, 2, 1),
]

_EQUIPOS_INICIALES = [
    ('TEÑIDORA MAQ 38',                  'TEÑ1',      'BRAZZOLI',               'Tintorería', 'TINTORERIA', True),
    ('TEÑIDORA MAQ 32',                  'TEÑ2',      'MCS',                    'Tintorería', 'TINTORERIA', False),
    ('TEÑIDORA MAQ 35',                  'TEÑ3',      'BRAZZOLI',               'Tintorería', 'TINTORERIA', False),
    ('TEÑIDORA MAQ 29',                  'TEÑ4',      'MCS',                    'Tintorería', 'TINTORERIA', False),
    ('TEÑIDORA MAQ 34',                  'TEÑ5',      'BRAZZOLI',               'Tintorería', 'TINTORERIA', False),
    ('TEÑIDORA MAQ 35',                  'TEÑ6',      'BRAZZOLI',               'Tintorería', 'TINTORERIA', False),
    ('TEÑIDORA MAQ 37',                  'TEÑ7',      'BRAZZOLI',               'Tintorería', 'TINTORERIA', False),
    ('TEÑIDORA MAQ 20',                  'TEÑ8',      'MCS',                    'Tintorería', 'TINTORERIA', False),
    ('TEÑIDORA MAQ 12',                  'TEÑ9',      'MCS',                    'Tintorería', 'TINTORERIA', False),
    ('TEÑIDORA MAQ 11',                  'TEÑ10',     'MCS',                    'Tintorería', 'TINTORERIA', False),
    ('TEÑIDORA MAQ 10',                  'TEÑ11',     'MCS',                    'Tintorería', 'TINTORERIA', False),
    ('TEÑIDORA MAQ 9',                   'TEÑ12',     'DANITECH',               'Tintorería', 'TINTORERIA', False),
    ('TEÑIDORA MAQ 8',                   'TEÑ13',     'DANITECH',               'Tintorería', 'TINTORERIA', False),
    ('TEÑIDORA MAQ 7',                   'TEÑ14',     'BRAZZOLI',               'Tintorería', 'TINTORERIA', False),
    ('TEÑIDORA MAQ 1',                   'TEÑ15',     'THIES',                  'Tintorería', 'TINTORERIA', False),
    ('TEÑIDORA MAQ 2',                   'TEÑ16',     'THIES',                  'Tintorería', 'TINTORERIA', False),
    ('TEÑIDORA MAQ 3',                   'TEÑ17',     'THIES',                  'Tintorería', 'TINTORERIA', False),
    ('TEÑIDORA MAQ 4',                   'TEÑ18',     'THIES',                  'Tintorería', 'TINTORERIA', False),
    ('TEÑIDORA MAQ 5',                   'TEÑ19',     'THIES',                  'Tintorería', 'TINTORERIA', False),
    ('TEÑIDORA MAQ 6',                   'TEÑ20',     'FONG',                   'Tintorería', 'TINTORERIA', False),
    ('TERMOFIJADO MESDAN MAQ 1',         'TEÑ21',     'TERMOFIJADO MESDAN',     'Tintorería', 'TINTORERIA', False),
    ('BIANCALANI MAQ 1',                 'TEÑ22',     'BIANCALANI',             'Tintorería', 'TINTORERIA', False),
    ('ABRIDORA MAQ 1',                   'TEÑ23',     'ABRIDORA',               'Tintorería', 'TINTORERIA', False),
    ('ABRIDORA MAQ 2',                   'TEÑ24',     'ABRIDORA',               'Tintorería', 'TINTORERIA', False),
    ('HIDROEXTRACTORA CORINO MAQ 1',     'TEÑ25',     'HIDROEXTRACTORA CORINO', 'Tintorería', 'TINTORERIA', False),
    ('HIDROEXTRACTORA BIANCO MAQ 1',     'TEÑ26',     'HIDROEXTRACTORA BIANCO', 'Tintorería', 'TINTORERIA', False),
    ('LISTADORA MAQ 1',                  'TEJ1',      'BIOTEX',                 'Tejeduría',  'TEJEDURIA',  False),
    ('LISTADORA MAQ 2',                  'TEJ2',      'MAYER',                  'Tejeduría',  'TEJEDURIA',  False),
    ('LISTADORA MAQ 3',                  'TEJ3',      'MAYER',                  'Tejeduría',  'TEJEDURIA',  False),
    ('LISTADORA MAQ 4',                  'TEJ4',      'MAYER',                  'Tejeduría',  'TEJEDURIA',  False),
    ('LISTADORA MAQ 5',                  'TEJ5',      'MAYER',                  'Tejeduría',  'TEJEDURIA',  False),
    ('LISTADORA MAQ 6',                  'TEJ6',      'BIOTEX',                 'Tejeduría',  'TEJEDURIA',  False),
    ('LISTADORA MAQ 7',                  'TEJ7',      'MAYER',                  'Tejeduría',  'TEJEDURIA',  False),
    ('LISTADORA MAQ 8',                  'TEJ8',      'MAYER',                  'Tejeduría',  'TEJEDURIA',  False),
    ('LISTADORA MAQ 9',                  'TEJ9',      'MAYER',                  'Tejeduría',  'TEJEDURIA',  False),
    ('JERSERA MAQ 10',                   'TEJ10',     'SANYONG',                'Tejeduría',  'TEJEDURIA',  False),
    ('JERSERA MAQ 11',                   'TEJ11',     'BIOTEX',                 'Tejeduría',  'TEJEDURIA',  False),
    ('GAMUZA MAQ 12',                    'TEJ12',     'BIOTEX',                 'Tejeduría',  'TEJEDURIA',  False),
    ('JERSERA MAQ 14',                   'TEJ14',     'BIOTEX',                 'Tejeduría',  'TEJEDURIA',  False),
    ('JERSERA MAQ 15',                   'TEJ15',     'BIOTEX',                 'Tejeduría',  'TEJEDURIA',  False),
    ('GAMUZA MAQ 16',                    'TEJ16',     'BIOTEX',                 'Tejeduría',  'TEJEDURIA',  False),
    ('JERSERA MAQ 17',                   'TEJ17',     'MAYER',                  'Tejeduría',  'TEJEDURIA',  False),
    ('JERSERA MAQ 18',                   'TEJ18',     'MAYER',                  'Tejeduría',  'TEJEDURIA',  False),
    ('RIPERA MAQ 19',                    'TEJ19',     'BIOTEX',                 'Tejeduría',  'TEJEDURIA',  False),
    ('GAMUZA MAQ 20',                    'TEJ20',     'BIOTEX',                 'Tejeduría',  'TEJEDURIA',  False),
    ('GAMUZA MAQ 21',                    'TEJ21',     'BIOTEX',                 'Tejeduría',  'TEJEDURIA',  False),
    ('RIPERA MAQ 22',                    'TEJ22',     'BIOTEX',                 'Tejeduría',  'TEJEDURIA',  False),
    ('RIPERA MAQ 23',                    'TEJ23',     'BIOTEX',                 'Tejeduría',  'TEJEDURIA',  False),
    ('RIPERA MAQ 24',                    'TEJ24',     'BIOTEX',                 'Tejeduría',  'TEJEDURIA',  False),
    ('JERSERA MAQ 25',                   'TEJ25',     'MAYER',                  'Tejeduría',  'TEJEDURIA',  False),
    ('RIPERA MAQ 26',                    'TEJ26',     'ORIZIO',                 'Tejeduría',  'TEJEDURIA',  False),
    ('JERSERA MAQ 27',                   'TEJ27',     'MAYER',                  'Tejeduría',  'TEJEDURIA',  False),
    ('JERSERA MAQ 28',                   'TEJ28',     'MAYER',                  'Tejeduría',  'TEJEDURIA',  False),
    ('JERSERA MAQ 29',                   'TEJ29',     'MAYER',                  'Tejeduría',  'TEJEDURIA',  False),
    ('JERSERA MAQ 30',                   'TEJ30',     'MAYER',                  'Tejeduría',  'TEJEDURIA',  False),
    ('JERSERA MAQ 31',                   'TEJ31',     'MAYER',                  'Tejeduría',  'TEJEDURIA',  False),
    ('JERSERA MAQ 32',                   'TEJ32',     'MAYER',                  'Tejeduría',  'TEJEDURIA',  False),
    ('JERSERA MAQ 33',                   'TEJ33',     'MAYER',                  'Tejeduría',  'TEJEDURIA',  False),
    ('JERSERA MAQ 34',                   'TEJ34',     'MAYER',                  'Tejeduría',  'TEJEDURIA',  False),
    ('JERSERA MAQ 35',                   'TEJ35',     'MAYER',                  'Tejeduría',  'TEJEDURIA',  False),
    ('JERSERA MAQ 36',                   'TEJ36',     'MAYER',                  'Tejeduría',  'TEJEDURIA',  False),
    ('JERSERA MAQ 37',                   'TEJ37',     'MAYER',                  'Tejeduría',  'TEJEDURIA',  False),
    ('JERSERA MAQ 38',                   'TEJ38',     'MAYER',                  'Tejeduría',  'TEJEDURIA',  False),
    ('JERSERA MAQ 39',                   'TEJ39',     'MAYER',                  'Tejeduría',  'TEJEDURIA',  False),
    ('JERSERA MAQ 40',                   'TEJ40',     'MAYER',                  'Tejeduría',  'TEJEDURIA',  False),
    ('JERSERA MAQ 41',                   'TEJ41',     'MAYER',                  'Tejeduría',  'TEJEDURIA',  False),
    ('JERSERA MAQ 42',                   'TEJ42',     'MAYER',                  'Tejeduría',  'TEJEDURIA',  False),
    ('JERSERA MAQ 43',                   'TEJ43',     'MAYER',                  'Tejeduría',  'TEJEDURIA',  False),
    ('JERSERA MAQ 44',                   'TEJ44',     'MAYER',                  'Tejeduría',  'TEJEDURIA',  False),
    ('JERSERA MAQ 45',                   'TEJ45',     'MAYER',                  'Tejeduría',  'TEJEDURIA',  False),
    ('JERSERA MAQ 46',                   'TEJ46',     'MAYER',                  'Tejeduría',  'TEJEDURIA',  False),
    ('JERSERA MAQ 47',                   'TEJ47',     'MAYER',                  'Tejeduría',  'TEJEDURIA',  False),
    ('JERSERA MAQ 48',                   'TEJ48',     'HAVERTEX',               'Tejeduría',  'TEJEDURIA',  False),
    ('JERSERA MAQ 49',                   'TEJ49',     'HAVERTEX',               'Tejeduría',  'TEJEDURIA',  False),
    ('JERSERA MAQ 50',                   'TEJ50',     'ORIZIO',                 'Tejeduría',  'TEJEDURIA',  False),
    ('GAMUZA MAQ 51',                    'TEJ51',     'BIOTEX',                 'Tejeduría',  'TEJEDURIA',  False),
    ('GAMUZA MAQ 52',                    'TEJ52',     'BIOTEX',                 'Tejeduría',  'TEJEDURIA',  False),
    ('RIPERA MAQ 53',                    'TEJ53',     'BIOTEX',                 'Tejeduría',  'TEJEDURIA',  False),
    ('RIPERA MAQ 54',                    'TEJ54',     'BIOTEX',                 'Tejeduría',  'TEJEDURIA',  False),
    ('JERSERA MAQ 55',                   'TEJ55',     'BECK',                   'Tejeduría',  'TEJEDURIA',  False),
    ('RIPERA MAQ 56',                    'TEJ56',     'MAYER',                  'Tejeduría',  'TEJEDURIA',  False),
    ('GAMUZA MAQ 57',                    'TEJ57',     'MAYER',                  'Tejeduría',  'TEJEDURIA',  False),
    ('GAMUZA MAQ 58',                    'TEJ58',     'MAYER',                  'Tejeduría',  'TEJEDURIA',  False),
    ('RIPERA MAQ 59',                    'TEJ59',     'ORIZIO',                 'Tejeduría',  'TEJEDURIA',  False),
    ('RIPERA MAQ 60',                    'TEJ60',     'MAYER',                  'Tejeduría',  'TEJEDURIA',  False),
    ('RIPERA MAQ 61',                    'TEJ61',     'MAYER',                  'Tejeduría',  'TEJEDURIA',  False),
    ('RIPERA MAQ 62',                    'TEJ62',     'MAYER',                  'Tejeduría',  'TEJEDURIA',  False),
    ('RIPERA MAQ 63',                    'TEJ63',     'MAYER',                  'Tejeduría',  'TEJEDURIA',  False),
    ('RIPERA MAQ 64',                    'TEJ64',     'ORIZIO',                 'Tejeduría',  'TEJEDURIA',  False),
    ('RIPERA MAQ 65',                    'TEJ65',     'ORIZIO',                 'Tejeduría',  'TEJEDURIA',  False),
    ('RIPERA MAQ 66',                    'TEJ66',     'MAYER',                  'Tejeduría',  'TEJEDURIA',  False),
    ('RIPERA MAQ 67',                    'TEJ67',     'MAYER',                  'Tejeduría',  'TEJEDURIA',  False),
    ('RIPERA MAQ 68',                    'TEJ68',     'MAYER',                  'Tejeduría',  'TEJEDURIA',  False),
    ('JERSERA MAQ 69',                   'TEJ69',     'MAYER',                  'Tejeduría',  'TEJEDURIA',  False),
    ('JERSERA MAQ 70',                   'TEJ70',     'BECK',                   'Tejeduría',  'TEJEDURIA',  False),
    ('FELPA MAQ 71',                     'TEJ71',     'BECK',                   'Tejeduría',  'TEJEDURIA',  False),
    ('JERSERA MAQ 72',                   'TEJ72',     'MAYER',                  'Tejeduría',  'TEJEDURIA',  False),
    ('RIPERA MAQ 73',                    'TEJ73',     'ORIZIO',                 'Tejeduría',  'TEJEDURIA',  False),
    ('RIPERA MAQ 74',                    'TEJ74',     'ORIZIO',                 'Tejeduría',  'TEJEDURIA',  False),
    ('JERSERA MAQ 75',                   'TEJ75',     'MAYER',                  'Tejeduría',  'TEJEDURIA',  False),
    ('FRANELA 3 HILOS MAQ 76',           'TEJ76',     'ORIZIO',                 'Tejeduría',  'TEJEDURIA',  False),
    ('JERSERA MAQ 77',                   'TEJ77',     'ORIZIO',                 'Tejeduría',  'TEJEDURIA',  False),
    ('RIPERA MAQ 78',                    'TEJ78',     'ORIZIO',                 'Tejeduría',  'TEJEDURIA',  False),
    ('RIPERA MAQ 79',                    'TEJ79',     'ORIZIO',                 'Tejeduría',  'TEJEDURIA',  False),
    ('RIPERA MAQ 80',                    'TEJ80',     'ORIZIO',                 'Tejeduría',  'TEJEDURIA',  False),
    ('RIPERA MAQ 81',                    'TEJ81',     'ORIZIO',                 'Tejeduría',  'TEJEDURIA',  False),
    ('JERSERA MAQ 82',                   'TEJ82',     'ORIZIO',                 'Tejeduría',  'TEJEDURIA',  False),
    ('JERSERA MAQ 83',                   'TEJ83',     'ORIZIO',                 'Tejeduría',  'TEJEDURIA',  False),
    ('RIPERA MAQ 84',                    'TEJ84',     'ORIZIO',                 'Tejeduría',  'TEJEDURIA',  False),
    ('RIPERA MAQ 85',                    'TEJ85',     'ORIZIO',                 'Tejeduría',  'TEJEDURIA',  False),
    ('RIPERA MAQ 86',                    'TEJ86',     'SANTEX',                 'Tejeduría',  'TEJEDURIA',  False),
    ('RIPERA MAQ 87',                    'TEJ87',     'MAYER',                  'Tejeduría',  'TEJEDURIA',  False),
    ('GAMUZA MAQ 88',                    'TEJ88',     'ORIZIO',                 'Tejeduría',  'TEJEDURIA',  False),
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
    _track_owned(env, 'hr.department', dept.id, f'dept_{_slug(nombre)}_{company.id}')
    return dept


def _create_initial_equipment(env):
    """Crea/actualiza los equipos iniciales. Ya NO crea ni vincula ningún
    mrp.workcenter — el área de una máquina es su hr.department
    (Tejeduría/Tintorería). El puente con las órdenes de trabajo reales
    (que sí usan mrp.workcenter, de otra compañía) se hace por departamento
    en `idtx_mrp` — ver [[project_workcenter_check_company]]. Un equipo de
    IDETEX no puede apuntar al centro de trabajo real de otra compañía sin
    romper su configuración (`check_company`), así que no hace falta ni
    conviene crear uno propio solo para este enlace."""
    Equipment = env['maintenance.equipment'].with_context(lang='en_US')
    fields_eq = Equipment._fields
    tiene_department = 'department_id' in fields_eq
    tiene_idtx = 'enabled' in fields_eq

    depts = {}
    if tiene_department:
        try:
            for nombre_dept in ('Tintorería', 'Tejeduría'):
                depts[nombre_dept] = _get_or_create_department(env, nombre_dept)
        except Exception:
            _logger.warning('Plan General Alpha: no se pudieron crear departamentos HR.', exc_info=True)
            tiene_department = False

    tiene_machine_state = 'machine_state' in fields_eq

    creados = renombrados = omitidos = 0
    for nombre, serial_no, modelo, dept_nombre, _wc_nombre, habilitado in _EQUIPOS_INICIALES:
        eq = Equipment.search([('serial_no', '=', serial_no)], limit=1)

        if not eq:
            m = re.match(r'^TE[ÑN](\d+)$', serial_no)
            if m:
                eq = Equipment.search([('serial_no', '=', m.group(1))], limit=1)

        if eq:
            vals_upd = {}
            if eq.name != nombre:
                vals_upd['name'] = nombre
            if eq.serial_no != serial_no:
                vals_upd['serial_no'] = serial_no
            if vals_upd:
                try:
                    eq.write(vals_upd)
                    renombrados += 1
                except Exception:
                    _logger.warning(
                        'Plan General Alpha: no se pudo renombrar equipo "%s".', nombre, exc_info=True
                    )
            else:
                omitidos += 1
            _track_owned(env, 'maintenance.equipment', eq.id, f'equip_{_slug(serial_no)}')
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
        if tiene_idtx:
            vals['enabled'] = habilitado
            vals['oos'] = False
        if tiene_machine_state:
            vals['machine_state'] = 'operativa'
        try:
            eq_new = Equipment.create(vals)
            _track_owned(env, 'maintenance.equipment', eq_new.id, f'equip_{_slug(serial_no)}')
            creados += 1
        except Exception:
            _logger.warning('Plan General Alpha: no se pudo crear equipo "%s".', nombre, exc_info=True)

    _logger.info(
        'Plan General Alpha: equipos iniciales — %d creados, %d renombrados, %d ya estaban al día.',
        creados, renombrados, omitidos,
    )


def _create_floor_layouts(env, workcenter, layout_data):
    """Crea/corrige las posiciones de cuadrícula para un centro de trabajo.
    Cada entrada de layout_data es (serial_no, slot_index) o
    (serial_no, slot_index, span_cols, span_rows) — sin span se asume 1x1."""
    if 'idtx.alpha.floor.layout' not in env.registry.models:
        _logger.warning('Plan General Alpha: modelo idtx.alpha.floor.layout no disponible.')
        return
    Layout = env['idtx.alpha.floor.layout']
    Equipment = env['maintenance.equipment']

    creados = corregidos = 0
    for entry in layout_data:
        serial_no, slot_index, *span = entry
        span_cols, span_rows = (span[0], span[1]) if len(span) == 2 else (1, 1)

        eq = Equipment.search([('serial_no', '=', serial_no)], limit=1)
        if not eq:
            _logger.debug('Plan General Alpha: equipo %s no encontrado, omitiendo layout.', serial_no)
            continue
        existing = Layout.search([
            ('equipment_id', '=', eq.id),
            ('workcenter', '=', workcenter),
        ], limit=1)
        try:
            if existing:
                if (existing.slot_index != slot_index
                        or existing.span_cols != span_cols or existing.span_rows != span_rows):
                    existing.write({
                        'slot_index': slot_index, 'span_cols': span_cols, 'span_rows': span_rows,
                    })
                    corregidos += 1
            else:
                Layout.create({
                    'equipment_id': eq.id,
                    'workcenter': workcenter,
                    'slot_index': slot_index,
                    'span_cols': span_cols,
                    'span_rows': span_rows,
                })
                creados += 1
        except Exception:
            _logger.warning(
                'Plan General Alpha: no se pudo aplicar layout para %s.', serial_no, exc_info=True
            )

    _logger.info(
        'Plan General Alpha: floor layout %s — %d creados, %d corregidos.',
        workcenter, creados, corregidos,
    )


def _set_tejeduria_operativa(env):
    """Fuerza a 'operativa' el estado de todas las máquinas del centro de trabajo TEJEDURIA."""
    Equipment = env['maintenance.equipment']
    if 'machine_state' not in Equipment._fields:
        return

    domain = [('active', '=', True)]
    dept = env['hr.department'].search([('name', 'ilike', 'Tejed')], limit=1)
    if not dept:
        return
    domain.append(('department_id', '=', dept.id))

    maquinas = Equipment.search(domain)
    por_cambiar = maquinas.filtered(lambda m: m.machine_state != 'operativa')
    if por_cambiar:
        por_cambiar.write({'machine_state': 'operativa'})
    _logger.info(
        'Plan General Alpha: TEJEDURIA operativa — %d máquinas actualizadas de %d totales.',
        len(por_cambiar), len(maquinas),
    )


def post_init_hook(env):
    # El tablero board.board legacy (gráficas de control.pedido) se retiró con
    # SITPRO/TEXPLUS. El tablero vigente es el componente OWL (plan_alpha_dashboard).
    _create_initial_equipment(env)
    _create_floor_layouts(env, 'TEJEDURIA', _TEJEDURIA_FLOOR_LAYOUT)
    _create_floor_layouts(env, 'TINTORERIA', _TINTORERIA_FLOOR_LAYOUT)
    _set_tejeduria_operativa(env)
