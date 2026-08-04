import logging

from odoo import _, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# Parámetros por defecto (ir.config_parameter los sobreescribe).
# OJO: el servidor ORGATEX corre DOS instancias con named pipes y puertos
# DINÁMICOS, no el 1433: SETEX (49274, base ORGATEX del sistema de teñido) y
# SQLEXPRESS (49264, base ORGATEX-INTEG que es la de integración, donde se
# insertan los dyelots). El DSN heredado apuntaba al 1433 (cerrado).
ORGATEX_DEFAULTS = {
    'idtx_orgatex.host': '182.16.60.1',
    'idtx_orgatex.port': '49264',
    'idtx_orgatex.database': 'ORGATEX-INTEG',
    'idtx_orgatex.user': 'orgatex',
    'idtx_orgatex.password': 'orgatex',
    'idtx_orgatex.enabled': 'False',
}


class OrgatexConnectionMixin(models.AbstractModel):
    """Conexión a la base de integración de ORGATEX (SQL Server 2012)."""
    _name = 'orgatex.connection.mixin'
    _description = 'Conexión ORGATEX'

    def _orgatex_param(self, key):
        return self.env['ir.config_parameter'].sudo().get_param(
            key, ORGATEX_DEFAULTS.get(key, ''))

    def _orgatex_write_enabled(self):
        """Guarda de escritura: en dev queda apagado para no insertar dyelots
        reales en la planta (mismo criterio que texplus_write_enabled)."""
        return self._orgatex_param('idtx_orgatex.enabled').strip().lower() in (
            '1', 'true', 'yes', 'y')

    def _orgatex_connect(self):
        """Devuelve una conexión pyodbc. ClientCharset y Encryption=off son
        NECESARIOS con FreeTDS contra este servidor: sin ellos el driver
        rechaza la conexión ('Unable to connect to data source')."""
        try:
            import pyodbc
        except ImportError:
            raise UserError(_('Falta el paquete pyodbc en el servidor Odoo.'))
        conn_str = (
            'DRIVER=FreeTDS;'
            'SERVER=%(host)s;PORT=%(port)s;DATABASE=%(db)s;'
            'UID=%(user)s;PWD=%(pwd)s;'
            'TDS_Version=7.3;ClientCharset=UTF-8;Encryption=off;'
        ) % {
            'host': self._orgatex_param('idtx_orgatex.host'),
            'port': self._orgatex_param('idtx_orgatex.port'),
            'db': self._orgatex_param('idtx_orgatex.database'),
            'user': self._orgatex_param('idtx_orgatex.user'),
            'pwd': self._orgatex_param('idtx_orgatex.password'),
        }
        try:
            return pyodbc.connect(conn_str, timeout=15)
        except Exception as exc:
            _logger.exception('ORGATEX: fallo de conexión')
            raise UserError(_(
                'No se pudo conectar con ORGATEX (%(host)s:%(port)s/%(db)s):\n%(err)s',
                host=self._orgatex_param('idtx_orgatex.host'),
                port=self._orgatex_param('idtx_orgatex.port'),
                db=self._orgatex_param('idtx_orgatex.database'),
                err=exc))

    def action_test_orgatex_connection(self):
        conn = self._orgatex_connect()
        try:
            cur = conn.cursor()
            cur.execute('SELECT DB_NAME(), @@SERVERNAME')
            db, server = cur.fetchone()
            cur.close()
        finally:
            conn.close()
        modo = _('ESCRITURA HABILITADA') if self._orgatex_write_enabled() \
            else _('solo lectura (escritura deshabilitada)')
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': 'success',
                'title': _('Conexión ORGATEX correcta'),
                'message': _('Base %(db)s en %(server)s — %(modo)s.',
                             db=db, server=server, modo=modo),
                'sticky': False,
            },
        }
