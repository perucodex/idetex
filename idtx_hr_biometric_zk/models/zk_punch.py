# -*- coding: utf-8 -*-
from datetime import timedelta

import pytz

from odoo import models, fields, api

DEVICE_TZ = 'America/Lima'


class ZkPunch(models.Model):
    """Marcación CRUDA del biométrico (una fila por huella/rostro leído).

    hr.attendance guarda solo el par entrada/salida del día; aquí se conserva
    cada marca con su tipo (I/O) para poder auditar dobles marcaciones y
    reconstruir historia. Se llena en la sincronización del equipo y por
    importes históricos (Access del ZKTime).
    """
    _name = 'zk.punch'
    _description = 'Marcación cruda del biométrico'
    _order = 'punch_time desc'

    employee_id = fields.Many2one(
        'hr.employee', string='Empleado', required=True, index=True, ondelete='cascade')
    device_id = fields.Many2one('zk.device', string='Equipo', ondelete='set null')
    punch_time = fields.Datetime(string='Fecha/Hora (UTC)', required=True, index=True)
    punch_type = fields.Selection([
        ('i', 'Ingreso'),
        ('o', 'Salida'),
        ('x', 'Sin tipo'),
    ], string='Tipo', default='x', required=True,
        help="Tipo de marca reportado por el reloj (CHECKTYPE). Algunos "
             "equipos no lo informan ('Sin tipo').")
    day = fields.Date(string='Día', compute='_compute_day', store=True, index=True,
                      help="Día LOCAL (America/Lima) de la marca.")

    _punch_uniq = models.Constraint(
        'unique(employee_id, punch_time)',
        'Esta marcación ya está registrada para el empleado.')

    @api.depends('punch_time')
    def _compute_day(self):
        tz = pytz.timezone(DEVICE_TZ)
        for rec in self:
            if rec.punch_time:
                rec.day = pytz.UTC.localize(rec.punch_time).astimezone(tz).date()
            else:
                rec.day = False

    # ------------------------------------------------------------------
    #  Rearmado de asistencias (sesiones que pueden cruzar medianoche)
    # ------------------------------------------------------------------
    @api.model
    def _rebuild_attendances(self, employee_ids, date_from, date_to):
        """Reconstruye hr.attendance desde las marcas crudas para los
        empleados y rango de DÍAS locales dados. Sesiona por turno:
        - ingreso de día (< 14:00): la salida es del mismo día.
        - ingreso de tarde/noche (>= 14:00, obrero): la salida es la marca de
          la mañana siguiente (una sola asistencia que cruza medianoche).
        Marca el turno (día/noche) en la asistencia. Idempotente: borra las
        asistencias del rango de esos empleados y las vuelve a crear.
        Devuelve nº de asistencias creadas."""
        from datetime import datetime, timedelta
        import pytz
        tz = pytz.timezone(DEVICE_TZ)
        utc = pytz.UTC
        NIGHT_CUT = 14.0

        emps = self.env['hr.employee'].with_context(active_test=False).browse(employee_ids)
        # ventana UTC que cubre el rango local (+1 día por sesiones nocturnas)
        ds = tz.localize(datetime.combine(date_from, datetime.min.time()))
        de = tz.localize(datetime.combine(date_to + timedelta(days=2), datetime.min.time()))
        ds_utc = ds.astimezone(utc).replace(tzinfo=None)
        de_utc = de.astimezone(utc).replace(tzinfo=None)

        Att = self.env['hr.attendance'].with_context(
            hr_attendance_bypass_validation=True)
        created = 0
        for emp in emps:
            punches = self.search([
                ('employee_id', '=', emp.id),
                ('punch_time', '>=', ds_utc), ('punch_time', '<', de_utc)],
                order='punch_time')
            locs = [utc.localize(p.punch_time).astimezone(tz) for p in punches]
            sessions = []
            i, n = 0, len(locs)
            while i < n:
                e = locs[i]
                eh = e.hour + e.minute / 60.0
                if eh >= NIGHT_CUT:
                    wend = tz.localize(datetime.combine(
                        e.date() + timedelta(days=1), datetime.min.time().replace(hour=14)))
                    shift = 'night'
                else:
                    wend = tz.localize(datetime.combine(
                        e.date(), datetime.max.time()))
                    shift = 'day'
                j = i
                while j < n and locs[j] <= wend:
                    j += 1
                sess = locs[i:j]
                # la sesión debe caer (por su ingreso) dentro del rango pedido
                if date_from <= sess[0].date() <= date_to:
                    ci = sess[0]
                    co = sess[-1] if (len(sess) > 1 and sess[-1] > sess[0]) else sess[0]
                    sessions.append((ci, co, shift))
                i = j

            # borrar asistencias existentes cuyo INGRESO cae en el rango local
            existing = Att.search([
                ('employee_id', '=', emp.id),
                ('check_in', '>=', ds_utc), ('check_in', '<', de_utc)])
            existing = existing.filtered(
                lambda a: date_from <= utc.localize(a.check_in).astimezone(tz).date() <= date_to)
            if existing:
                existing.unlink()
            for ci, co, shift in sessions:
                Att.create({
                    'employee_id': emp.id,
                    'check_in': ci.astimezone(utc).replace(tzinfo=None),
                    'check_out': co.astimezone(utc).replace(tzinfo=None),
                    'l10n_pe_shift': shift,
                })
                created += 1
        return created

    @api.model
    def _register_punches(self, rows):
        """Crea las marcas que falten. rows = [(employee_id, punch_time_utc,
        punch_type, device_id)]. Idempotente. Devuelve cuántas creó."""
        if not rows:
            return 0
        emp_ids = {r[0] for r in rows}
        tmin = min(r[1] for r in rows) - timedelta(seconds=1)
        tmax = max(r[1] for r in rows) + timedelta(seconds=1)
        existing = {
            (p.employee_id.id, p.punch_time)
            for p in self.search([('employee_id', 'in', list(emp_ids)),
                                  ('punch_time', '>=', tmin), ('punch_time', '<=', tmax)])
        }
        vals = [
            {'employee_id': e, 'punch_time': t, 'punch_type': pt or 'x', 'device_id': d}
            for e, t, pt, d in {(r[0], r[1], r[2], r[3]) for r in rows}
            if (e, t) not in existing
        ]
        if vals:
            self.create(vals)
        return len(vals)
