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

    # Ingreso a esta hora local (float) o después => turno NOCHE (obrero); su
    # salida es la marca de la mañana siguiente (sesión que cruza medianoche).
    NIGHT_CUT = 14.0

    # ------------------------------------------------------------------
    #  Rearmado de asistencias (sesiones que pueden cruzar medianoche)
    # ------------------------------------------------------------------
    def _sessions_for(self, employee_id, date_from, date_to):
        """Agrupa las marcas crudas del empleado en SESIONES de trabajo (una
        entrada + su salida, pudiendo cruzar medianoche). Es la fuente única
        de verdad tanto para armar hr.attendance como para detectar dobles /
        marca única en la revisión.

        Devuelve lista de dicts (sesiones cuyo INGRESO cae en [date_from,
        date_to], ordenadas): {'day', 'shift', 'check_in_utc', 'check_out_utc',
        'punches' (recordset ordenado)}."""
        from datetime import datetime, timedelta
        import pytz
        tz = pytz.timezone(DEVICE_TZ)
        utc = pytz.UTC
        ds = tz.localize(datetime.combine(date_from, datetime.min.time()))
        de = tz.localize(datetime.combine(date_to + timedelta(days=2), datetime.min.time()))
        ds_utc = ds.astimezone(utc).replace(tzinfo=None)
        de_utc = de.astimezone(utc).replace(tzinfo=None)

        punches = self.search([
            ('employee_id', '=', employee_id),
            ('punch_time', '>=', ds_utc), ('punch_time', '<', de_utc)],
            order='punch_time')
        locs = [utc.localize(p.punch_time).astimezone(tz) for p in punches]

        # El cruce de medianoche (turno noche) SOLO aplica a obreros rotativos
        # (employee_type='worker' + calendario de 2 semanas). Para el resto,
        # cada día local es una sesión de día (primera=entrada, última=salida).
        emp = self.env['hr.employee'].with_context(active_test=False).browse(employee_id)
        rotating = emp._is_rotating_worker()

        sessions = []
        i, n = 0, len(locs)
        while i < n:
            e = locs[i]
            eh = e.hour + e.minute / 60.0
            if rotating and eh >= self.NIGHT_CUT:
                wend = tz.localize(datetime.combine(
                    e.date() + timedelta(days=1), datetime.min.time().replace(hour=14)))
                shift = 'night'
            else:
                wend = tz.localize(datetime.combine(e.date(), datetime.max.time()))
                shift = 'day'
            j = i
            while j < n and locs[j] <= wend:
                j += 1
            sess_locs = locs[i:j]
            sess_punches = punches[i:j]
            if date_from <= sess_locs[0].date() <= date_to:
                ci = sess_locs[0]
                co = sess_locs[-1] if (len(sess_locs) > 1 and sess_locs[-1] > sess_locs[0]) else sess_locs[0]
                sessions.append({
                    'day': ci.date(),
                    'shift': shift,
                    'check_in_utc': ci.astimezone(utc).replace(tzinfo=None),
                    'check_out_utc': co.astimezone(utc).replace(tzinfo=None),
                    'punches': sess_punches,
                })
            i = j
        return sessions

    def _rebuild_attendances(self, employee_ids, date_from, date_to):
        """Reconstruye hr.attendance desde las sesiones (_sessions_for) de los
        empleados y rango de DÍAS locales dados. Marca el turno (día/noche).
        Idempotente: borra las asistencias del rango de esos empleados (por
        fecha de ingreso local) y las vuelve a crear. Devuelve nº creadas."""
        from datetime import datetime, timedelta
        import pytz
        tz = pytz.timezone(DEVICE_TZ)
        utc = pytz.UTC
        ds = tz.localize(datetime.combine(date_from, datetime.min.time()))
        de = tz.localize(datetime.combine(date_to + timedelta(days=2), datetime.min.time()))
        ds_utc = ds.astimezone(utc).replace(tzinfo=None)
        de_utc = de.astimezone(utc).replace(tzinfo=None)

        Att = self.env['hr.attendance'].with_context(
            hr_attendance_bypass_validation=True)
        created = 0
        for emp in self.env['hr.employee'].with_context(active_test=False).browse(employee_ids):
            sessions = self._sessions_for(emp.id, date_from, date_to)
            existing = Att.search([
                ('employee_id', '=', emp.id),
                ('check_in', '>=', ds_utc), ('check_in', '<', de_utc)])
            existing = existing.filtered(
                lambda a: date_from <= utc.localize(a.check_in).astimezone(tz).date() <= date_to)
            if existing:
                existing.unlink()
            for s in sessions:
                Att.create({
                    'employee_id': emp.id,
                    'check_in': s['check_in_utc'],
                    'check_out': s['check_out_utc'],
                    'l10n_pe_shift': s['shift'],
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
