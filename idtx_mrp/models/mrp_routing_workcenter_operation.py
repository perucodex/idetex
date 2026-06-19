# -*- coding: utf-8 -*-

import logging
import re
import unicodedata

import pyodbc

from odoo import _, fields, models
from odoo.exceptions import UserError
from odoo.tools import config


_logger = logging.getLogger(__name__)

pyodbc.setDecimalSeparator('.')


def _texplus_writes_enabled():
    """Devuelve True si esta instancia de Odoo puede ESCRIBIR en TEXPLUS.

    Las lecturas (SELECT) siempre siguen habilitadas. Esta bandera apaga
    solo los INSERT/UPDATE/DELETE/MERGE/TRUNCATE para evitar que un Odoo
    de desarrollo/staging corrompa el TEXPLUS de produccion (ambos suelen
    apuntar al mismo servidor SQL).

    Configuracion en odoo.conf:
        texplus_write_enabled = False   (apagado, modo lectura)
        texplus_write_enabled = True    (default, escritura habilitada)
    """
    val = config.get('texplus_write_enabled', True)
    if isinstance(val, str):
        return val.strip().lower() in ('1', 'true', 'yes', 'on')
    return bool(val)


_DML_PREFIXES = ('INSERT', 'UPDATE', 'DELETE', 'MERGE', 'TRUNCATE', 'CREATE', 'DROP', 'ALTER')


class _ReadOnlyTexplusCursor:
    """Proxy alrededor de pyodbc.Cursor que silenciosamente descarta DML.

    Cualquier INSERT/UPDATE/DELETE/etc. se loguea y no se ejecuta;
    rowcount queda en 0. SELECT y SET (configuracion de sesion) pasan
    intactos para no romper las lecturas.
    """
    _last_blocked = False

    def __init__(self, real_cursor):
        self._cursor = real_cursor

    def execute(self, sql, *args, **kwargs):
        head = sql.lstrip().upper()
        if head.startswith(_DML_PREFIXES):
            _logger.info(
                'TEXPLUS write blocked (texplus_write_enabled=False): %s',
                sql.strip()[:200],
            )
            self._last_blocked = True
            return self
        self._last_blocked = False
        return self._cursor.execute(sql, *args, **kwargs)

    def executemany(self, sql, seq_of_params):
        head = sql.lstrip().upper()
        if head.startswith(_DML_PREFIXES):
            _logger.info(
                'TEXPLUS write blocked (texplus_write_enabled=False): %s (batch=%s)',
                sql.strip()[:160], len(seq_of_params) if hasattr(seq_of_params, '__len__') else '?',
            )
            self._last_blocked = True
            return self
        self._last_blocked = False
        return self._cursor.executemany(sql, seq_of_params)

    @property
    def rowcount(self):
        if self._last_blocked:
            return 0
        return self._cursor.rowcount

    @property
    def description(self):
        return self._cursor.description

    def fetchone(self):
        if self._last_blocked:
            return None
        return self._cursor.fetchone()

    def fetchall(self):
        if self._last_blocked:
            return []
        return self._cursor.fetchall()

    def fetchmany(self, size=None):
        if self._last_blocked:
            return []
        return self._cursor.fetchmany(size) if size is not None else self._cursor.fetchmany()

    def close(self):
        return self._cursor.close()

    def __iter__(self):
        if self._last_blocked:
            return iter(())
        return iter(self._cursor)

    def __getattr__(self, name):
        return getattr(self._cursor, name)


class _ReadOnlyTexplusConnection:
    """Proxy alrededor de pyodbc.Connection. Solo las escrituras quedan
    bloqueadas — `commit()` se convierte en no-op (no hay DML), pero
    `rollback()` y `close()` siguen funcionando.
    """

    def __init__(self, real_conn):
        self._conn = real_conn

    def cursor(self):
        return _ReadOnlyTexplusCursor(self._conn.cursor())

    def commit(self):
        # No hubo escrituras reales; commit es no-op. Si hubo SELECTs
        # con isolation distinto a READ COMMITTED, pyodbc ya los maneja
        # implicitamente al cerrar la conexion.
        return None

    def rollback(self):
        return self._conn.rollback()

    def close(self):
        return self._conn.close()

    @property
    def timeout(self):
        return self._conn.timeout

    @timeout.setter
    def timeout(self, value):
        self._conn.timeout = value

    def __getattr__(self, name):
        return getattr(self._conn, name)


def _normalize_faspro_name(value):
    text = (str(value or '')).strip().upper()
    if not text:
        return ''
    text = ''.join(ch for ch in unicodedata.normalize('NFD', text) if unicodedata.category(ch) != 'Mn')
    text = re.sub(r'[^A-Z0-9]+', ' ', text)
    return re.sub(r'\s+', ' ', text).strip()


class MrpRoutingWorkcenterOperation(models.Model):
    _name = 'mrp.routing.workcenter.operation'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Workcenter Operation'

    name = fields.Char('Name', required=True)
    fas_code = fields.Char('Código MSSQL', help="Código correspondiente en la tabla FASPRO de MSSQL", copy=False)
    workcenter_id = fields.Many2one('mrp.workcenter', 'Work Center', required=True, check_company=True)
    # Fase padre para agrupar partidas. Auto-relación simple (sin nested-set):
    # se PERMITE que una fase sea su propio padre (auto-padre) para que las
    # partidas de una fase de nivel superior se agrupen bajo sí misma.
    parent_operation_id = fields.Many2one(
        'mrp.routing.workcenter.operation', string='Fase Padre',
        index=True, ondelete='set null',
        help="Fase padre para agrupar. Puede ser la misma fase (auto-padre).")
    child_operation_ids = fields.One2many(
        'mrp.routing.workcenter.operation', 'parent_operation_id',
        string='Sub-fases')
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
        index=True,
        required=True
    )
    parameter_ids = fields.One2many('operation.parameter', 'operation_id', string='Parameters')
    operation_type = fields.Selection(related='workcenter_id.operation_type')

    def _get_texplus_sql_connection(self):
        try:
            connection = pyodbc.connect(
                "DSN=ENBTEX1_DSN;"
                "PORT=1433;"
                "UID=sistemas;"
                "PWD=idtE#21@IRdc95;"
                "TDS_Version=7.3;"
                ,
                timeout=5,
            )
            connection.timeout = 10
        except Exception as error:
            raise UserError(_('No se pudo conectar a TEXPLUS SQL Server: %s') % error) from error
        # Modo solo-lectura: envuelve la conexion para que cualquier
        # INSERT/UPDATE/DELETE/MERGE/TRUNCATE sea descartado silenciosamente.
        # Esto protege a TEXPLUS de produccion cuando un Odoo de
        # desarrollo/staging apunta al mismo servidor SQL.
        if not _texplus_writes_enabled():
            return _ReadOnlyTexplusConnection(connection)
        return connection

    def _get_faspro_index(self):
        conn = None
        cursor = None
        try:
            conn = self._get_texplus_sql_connection()
            cursor = conn.cursor()
            cursor.execute('SET ARITHABORT ON')
            cursor.execute(
                """
                SELECT FasCod, FasDsc
                FROM dbo.FASPRO
                WHERE EmprCod = '001'
                  AND FasDsc IS NOT NULL
                ORDER BY FasCod
                """
            )
            faspro_by_name = {}
            faspro_by_code = {}
            for row in cursor.fetchall():
                code = (row.FasCod or '').strip()
                name = (row.FasDsc or '').strip()
                normalized_name = _normalize_faspro_name(name)
                if code:
                    faspro_by_code[code] = name
                if normalized_name and normalized_name not in faspro_by_name:
                    faspro_by_name[normalized_name] = code
            return faspro_by_name, faspro_by_code
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

    def action_sync_fas_code_from_texplus(self):
        operations = self or self.search([])
        faspro_by_name, faspro_by_code = self._get_faspro_index()

        updated_count = 0
        already_ok_count = 0
        not_found = []

        for operation in operations:
            normalized_name = _normalize_faspro_name(operation.name)
            matched_code = faspro_by_name.get(normalized_name)
            current_code = (operation.fas_code or '').strip()

            if not matched_code and current_code and current_code in faspro_by_code:
                matched_code = current_code

            if not matched_code:
                not_found.append(operation.name)
                continue

            if current_code == matched_code:
                already_ok_count += 1
                continue

            operation.fas_code = matched_code
            updated_count += 1

        message = _('Sincronizacion FASPRO completada. Actualizados: %s. Sin cambios: %s. Sin match: %s.') % (
            updated_count,
            already_ok_count,
            len(not_found),
        )
        if not_found:
            message = '%s %s' % (
                message,
                _('No encontrados: %s') % ', '.join(not_found[:10]),
            )

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Sincronizacion TEXPLUS'),
                'message': message,
                'type': 'success' if not not_found else 'warning',
                'sticky': bool(not_found),
            },
        }
