# -*- coding: utf-8 -*-
import logging
from datetime import datetime, timedelta

import pytz

from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# Los relojes guardan la hora local (Perú no usa horario de verano).
DEVICE_TZ = 'America/Lima'


class ZkDevice(models.Model):
    _name = 'zk.device'
    _description = 'Dispositivo Biométrico ZKTeco'

    name = fields.Char(string='Nombre', required=True)
    ip = fields.Char(string='Dirección IP', required=True)
    port = fields.Integer(string='Puerto', default=4370, required=True)
    timeout = fields.Integer(string='Timeout (s)', default=10)
    force_udp = fields.Boolean(string='Forzar UDP', default=False)
    comm_password = fields.Integer(string='Clave de comunicación', default=0)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        'res.company', string='Compañía', default=lambda self: self.env.company)
    last_sync = fields.Datetime(string='Última sincronización', readonly=True)
    lookback_days = fields.Integer(
        string='Días a revisar', default=60,
        help="Ventana de días hacia atrás que se procesa en cada sincronización. "
             "Las marcaciones más antiguas que esta ventana se ignoran.")

    # ------------------------------------------------------------------
    #  Conexión
    # ------------------------------------------------------------------
    def _get_connection(self):
        """Devuelve una conexión pyzk abierta al equipo (recordar cerrarla)."""
        self.ensure_one()
        try:
            from zk import ZK
        except ImportError:
            raise UserError(_(
                "Falta la librería 'pyzk' en el servidor de Odoo. "
                "Instálela con:  pip install pyzk"))
        zk = ZK(
            self.ip, port=self.port or 4370, timeout=self.timeout or 10,
            password=self.comm_password or 0, force_udp=self.force_udp,
            ommit_ping=False)
        try:
            return zk.connect()
        except Exception as e:  # noqa: BLE001
            raise UserError(_(
                "No se pudo conectar al equipo %(name)s (%(ip)s:%(port)s).\n%(err)s",
                name=self.name, ip=self.ip, port=self.port, err=e))

    def action_test_connection(self):
        self.ensure_one()
        conn = self._get_connection()
        try:
            try:
                device_name = conn.get_device_name()
            except Exception:  # noqa: BLE001
                device_name = self.name
        finally:
            conn.disconnect()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _("Conexión exitosa"),
                'message': _("Equipo: %s") % (device_name or self.ip),
                'type': 'success',
                'sticky': False,
            },
        }

    def action_sync(self):
        total = 0
        for device in self:
            total += device._sync_device()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _("Sincronización de marcaciones"),
                'message': _("%s registros de asistencia creados/actualizados.") % total,
                'type': 'success',
                'sticky': False,
            },
        }

    # ------------------------------------------------------------------
    #  Sincronización
    # ------------------------------------------------------------------
    def _employee_by_dni(self):
        """Mapa DNI -> empleado (incluye variante sin ceros a la izquierda)."""
        mapping = {}
        employees = self.env['hr.employee'].search([('identification_id', '!=', False)])
        for emp in employees:
            dni = (emp.identification_id or '').strip()
            if not dni:
                continue
            mapping.setdefault(dni, emp)
            mapping.setdefault(dni.lstrip('0'), emp)
        return mapping

    def _sync_device(self):
        """Descarga las marcaciones del equipo y crea/actualiza hr.attendance.

        Empareja por (empleado, día local): primera marca = entrada, última =
        salida (si solo hay una marca, entrada = salida). Idempotente: re-correr
        no duplica registros.
        """
        self.ensure_one()
        conn = self._get_connection()
        try:
            attendances = conn.get_attendance() or []
        finally:
            conn.disconnect()

        if not attendances:
            self.last_sync = fields.Datetime.now()
            return 0

        tz = pytz.timezone(DEVICE_TZ)
        utc = pytz.UTC
        min_date = fields.Date.context_today(self) - timedelta(days=self.lookback_days or 60)
        by_dni = self._employee_by_dni()

        # Agrupar marcaciones (en UTC) por (empleado, fecha local)
        groups = {}
        unmatched = set()
        matched_punches = 0
        skipped_old = 0
        for att in attendances:
            ts = getattr(att, 'timestamp', None)
            uid = str(getattr(att, 'user_id', '') or '').strip()
            if not ts or not uid:
                continue
            if ts.date() < min_date:
                skipped_old += 1
                continue
            emp = by_dni.get(uid) or by_dni.get(uid.lstrip('0'))
            if not emp:
                unmatched.add(uid)
                continue
            matched_punches += 1
            local_dt = tz.localize(ts) if ts.tzinfo is None else ts.astimezone(tz)
            utc_dt = local_dt.astimezone(utc).replace(tzinfo=None)
            groups.setdefault((emp.id, local_dt.date()), []).append(utc_dt)

        _logger.info(
            "ZK %s: get_attendance devolvió %s marcaciones | %s de empleados mapeados "
            "| %s descartadas por antigüedad | %s usuarios sin empleado | %s días agrupados",
            self.name, len(attendances), matched_punches, skipped_old,
            len(unmatched), len(groups))

        Attendance = self.env['hr.attendance']
        count = 0
        for (emp_id, day), times in groups.items():
            times.sort()
            check_in = times[0]
            check_out = times[-1] if (len(times) > 1 and times[-1] > times[0]) else times[0]

            # Rango UTC correspondiente al día local
            day_start = tz.localize(datetime(day.year, day.month, day.day))
            ds = day_start.astimezone(utc).replace(tzinfo=None)
            de = (day_start + timedelta(days=1)).astimezone(utc).replace(tzinfo=None)

            existing = Attendance.search([
                ('employee_id', '=', emp_id),
                ('check_in', '>=', ds),
                ('check_in', '<', de),
            ], limit=1)

            if existing:
                vals = {}
                if existing.check_in != check_in:
                    vals['check_in'] = check_in
                if existing.check_out != check_out:
                    vals['check_out'] = check_out
                if vals:
                    existing.write(vals)
                    count += 1
            else:
                Attendance.create({
                    'employee_id': emp_id,
                    'check_in': check_in,
                    'check_out': check_out,
                })
                count += 1

        if unmatched:
            _logger.warning(
                "ZK %s: usuarios sin empleado (DNI no encontrado en Odoo): %s",
                self.name, ', '.join(sorted(unmatched))[:500])

        self.last_sync = fields.Datetime.now()
        return count

    @api.model
    def _cron_sync_all(self):
        for device in self.search([('active', '=', True)]):
            try:
                device._sync_device()
            except Exception as e:  # noqa: BLE001
                _logger.exception("ZK: error sincronizando %s: %s", device.name, e)
