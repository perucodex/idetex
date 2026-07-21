# -*- coding: utf-8 -*-
from collections import defaultdict
from datetime import datetime, timedelta

import pytz

from odoo import models, fields, api, _
from odoo.exceptions import UserError

DEVICE_TZ = 'America/Lima'
LATE_TOLERANCE_MIN = 5


class ZkAttendanceReview(models.Model):
    """Revisión de marcaciones de un periodo, previa a la planilla.

    Detecta problemas (dobles marcas, marca única, faltas injustificadas,
    tardanzas) y deja que RRHH los resuelva uno a uno con trazabilidad:
    cada problema queda con estado corregido / aceptado y su chatter.
    """
    _name = 'zk.attendance.review'
    _description = 'Revisión de marcaciones (periodo)'
    _inherit = ['mail.thread']
    _order = 'date_from desc'

    name = fields.Char(string='Nombre', compute='_compute_name', store=True)
    date_from = fields.Date(string='Desde', required=True,
                            default=lambda self: fields.Date.context_today(self).replace(day=1))
    date_to = fields.Date(string='Hasta', required=True,
                          default=lambda self: fields.Date.context_today(self))
    company_id = fields.Many2one('res.company', string='Compañía', required=True,
                                 default=lambda self: self.env.company)
    issue_ids = fields.One2many('zk.attendance.issue', 'review_id', string='Problemas')
    issue_count = fields.Integer(compute='_compute_counts')
    pending_count = fields.Integer(string='Pendientes', compute='_compute_counts')

    @api.depends('date_from', 'date_to', 'company_id')
    def _compute_name(self):
        for rec in self:
            rec.name = _('Revisión %(df)s → %(dt)s (%(co)s)',
                         df=rec.date_from or '', dt=rec.date_to or '',
                         co=rec.company_id.name or '')

    @api.depends('issue_ids', 'issue_ids.state')
    def _compute_counts(self):
        for rec in self:
            rec.issue_count = len(rec.issue_ids)
            rec.pending_count = len(rec.issue_ids.filtered(lambda i: i.state == 'pending'))

    # ------------------------------------------------------------------
    #  Detección
    # ------------------------------------------------------------------
    def action_detect(self):
        self.ensure_one()
        if self.date_from > self.date_to:
            raise UserError(_('El rango de fechas es inválido.'))
        tz = pytz.timezone(DEVICE_TZ)
        utc = pytz.UTC
        Issue = self.env['zk.attendance.issue']

        ds = tz.localize(datetime.combine(self.date_from, datetime.min.time()))
        de = tz.localize(datetime.combine(self.date_to + timedelta(days=1), datetime.min.time()))
        ds_utc = ds.astimezone(utc).replace(tzinfo=None)
        de_utc = de.astimezone(utc).replace(tzinfo=None)

        cid = self.company_id.id
        Punch = self.env['zk.punch']

        # Empleados con marcas en el periodo (usan este reloj)
        punches = Punch.search([
            ('punch_time', '>=', ds_utc), ('punch_time', '<', de_utc),
            ('employee_id.company_id', '=', cid)])
        punch_emp_ids = set(punches.mapped('employee_id').ids)

        # Asistencias del periodo, indexadas por (empleado, día de ingreso)
        atts = self.env['hr.attendance'].search([
            ('check_in', '>=', ds_utc), ('check_in', '<', de_utc),
            ('employee_id.company_id', '=', cid)])
        att_by_emp_day = {}
        for a in atts:
            day = utc.localize(a.check_in).astimezone(tz).date()
            att_by_emp_day.setdefault((a.employee_id.id, day), a)

        # SESIONES por empleado (misma lógica que arma las asistencias: cruzan
        # medianoche), para detectar dobles/única sin partir los turnos noche.
        sessions_by_emp = {
            e: Punch._sessions_for(e, self.date_from, self.date_to)
            for e in punch_emp_ids
        }
        # días con sesión (para saber qué días el trabajador marcó/laboró)
        session_days = {(e, s['day']) for e, ss in sessions_by_emp.items() for s in ss}

        # Ausencias aprobadas (para no marcar falta)
        leaves = self.env['hr.leave'].search([
            ('state', '=', 'validate'),
            ('employee_id.company_id', '=', cid),
            ('request_date_from', '<=', self.date_to),
            ('request_date_to', '>=', self.date_from)])
        leave_days = set()
        for lv in leaves:
            d = lv.request_date_from
            while d <= lv.request_date_to:
                leave_days.add((lv.employee_id.id, d))
                d += timedelta(days=1)

        # Feriados (días festivos): resource.calendar.leaves SIN recurso. No son
        # inasistencias (el día está pagado). Se consideran los del calendario
        # global (company_id=False) y los de la compañía de la revisión.
        holiday_days = set()
        cal_leaves = self.env['resource.calendar.leaves'].sudo().search([
            ('resource_id', '=', False),
            ('date_from', '<=', de_utc), ('date_to', '>=', ds_utc),
            '|', ('company_id', '=', False), ('company_id', '=', cid)])
        for h in cal_leaves:
            d = utc.localize(h.date_from).astimezone(tz).date()
            end = utc.localize(h.date_to).astimezone(tz).date()
            while d <= end:
                holiday_days.add(d)
                d += timedelta(days=1)

        # Alcance de FALTAS: solo empleados activos que marcaron alguna vez
        # en el periodo (usan este reloj); evita ruido de otras sedes.
        emp_ids = punch_emp_ids | {e for e, _d in att_by_emp_day}
        employees = self.env['hr.employee'].browse(sorted(emp_ids))

        # Recalcular desde cero los PENDIENTES (así reflejan cambios de turno/
        # horario del empleado); los ya resueltos (corregido/aceptado) se
        # conservan como histórico y no se vuelven a crear.
        self.issue_ids.filtered(lambda i: i.state == 'pending').unlink()
        existing = {(i.employee_id.id, i.date, i.issue_type) for i in self.issue_ids}
        to_create = []

        emp_names = {e.id: e.name for e in employees}

        def add(emp_id, day, itype, desc, att=False, minutes=0.0):
            if (emp_id, day, itype) in existing:
                return
            existing.add((emp_id, day, itype))
            to_create.append({
                'review_id': self.id,
                'employee_id': emp_id,
                'employee_name': emp_names.get(emp_id),
                'date': day,
                'issue_type': itype,
                'description': desc,
                'attendance_id': att and att.id,
                'minutes_late': minutes,
            })

        fmt = lambda p: utc.localize(p.punch_time).astimezone(tz).strftime('%H:%M:%S')
        ptypes = dict(Punch._fields['punch_type'].selection)

        # 1) dobles marcas y 2) marca única — POR SESIÓN. Una sesión de 2
        # marcas separadas por un turno completo es entrada+salida aunque el
        # reloj las tipe igual (el reloj no siempre marca I/O bien): NO es
        # doble. Solo es doble cuando hay marcas EXTRA reales: 3+ marcas, o 2
        # del mismo tipo demasiado juntas (no alcanzan a ser un turno).
        MIN_SHIFT_HOURS = 4.0
        for emp_id, ss in sessions_by_emp.items():
            for s in ss:
                day = s['day']
                ps = s['punches'].sorted('punch_time')
                att = att_by_emp_day.get((emp_id, day))
                n = len(ps)
                if n == 1:
                    p = ps[0]
                    add(emp_id, day, 'single_punch',
                        _('Única marca del turno (%(t)s) a las %(h)s',
                          t=ptypes.get(p.punch_type), h=fmt(p)), att)
                    continue
                span_h = (ps[-1].punch_time - ps[0].punch_time).total_seconds() / 3600.0
                ins = ps.filtered(lambda p: p.punch_type == 'i')
                outs = ps.filtered(lambda p: p.punch_type == 'o')
                if n == 2:
                    # 2 marcas: si abarcan un turno => par entrada/salida normal.
                    # Si están muy juntas y del mismo tipo => doble redundante.
                    if span_h < MIN_SHIFT_HOURS and (len(ins) == 2 or len(outs) == 2):
                        tipo = 'double_in' if len(ins) == 2 else 'double_out'
                        verbo = _('ingreso') if len(ins) == 2 else _('salida')
                        add(emp_id, day, tipo,
                            _('Marcó %(v)s 2 veces seguidas: %(hs)s',
                              v=verbo, hs=', '.join(fmt(p) for p in ps)), att)
                    continue
                # 3+ marcas: hay marcas de más
                if len(ins) >= 2:
                    add(emp_id, day, 'double_in',
                        _('Marcó ingreso %(n)s veces: %(hs)s', n=len(ins),
                          hs=', '.join(fmt(p) for p in ins)), att)
                if len(outs) >= 2:
                    add(emp_id, day, 'double_out',
                        _('Marcó salida %(n)s veces: %(hs)s', n=len(outs),
                          hs=', '.join(fmt(p) for p in outs)), att)

        # 2bis) asistencia degenerada sin marcas crudas (historial antiguo)
        for (emp_id, day), att in att_by_emp_day.items():
            if (emp_id, day) in session_days:
                continue
            if att.check_in == att.check_out:
                h = utc.localize(att.check_in).astimezone(tz).strftime('%H:%M:%S')
                add(emp_id, day, 'single_punch',
                    _('Única marca del turno a las %(h)s (entrada = salida)', h=h), att)

        # 3) faltas y 4) tardanzas (turno deducido de la hora de ingreso)
        today = fields.Date.context_today(self)
        for emp in employees:
            if not emp.active:
                continue
            start_limit = emp.version_id.contract_date_start or self.date_from
            day = self.date_from
            while day <= self.date_to:
                if day >= today or day < start_limit:
                    day += timedelta(days=1)
                    continue
                att = att_by_emp_day.get((emp.id, day))
                has_punch = (emp.id, day) in session_days
                laborable = emp._is_laborable(day) and day not in holiday_days
                if not att and not has_punch:
                    if laborable and (emp.id, day) not in leave_days:
                        add(emp.id, day, 'absence',
                            _('Día laborable sin ninguna marcación ni ausencia justificada.'))
                elif att:
                    # Marca única (entrada = salida): no se puede saber si esa
                    # marca es ingreso o salida, así que NO se calcula tardanza
                    # (ya se reporta aparte como 'marca única').
                    if att.check_in == att.check_out:
                        day += timedelta(days=1)
                        continue
                    ci_local = utc.localize(att.check_in).astimezone(tz)
                    shift, expected = emp._attendance_shift_for(ci_local, day)
                    if expected is None:
                        day += timedelta(days=1)
                        continue
                    # Tardanza en minutos ENTEROS (se ignoran los segundos):
                    # marcar 08:05:59 = minuto 5 (dentro de tolerancia).
                    late = (ci_local.hour * 60 + ci_local.minute) - int(round(expected * 60))
                    # La tolerancia es un UMBRAL: si supera los 5 min se
                    # contabiliza la tardanza COMPLETA (6 → 6); 5 o menos → nada.
                    if late > LATE_TOLERANCE_MIN:
                        tno = _('noche') if shift == 'night' else _('día')
                        add(emp.id, day, 'late',
                            _('Ingresó %(h)s (turno %(t)s, programado %(e)02d:%(m)02d): '
                              '%(late)d min de tardanza.',
                              h=ci_local.strftime('%H:%M'), t=tno, e=int(expected),
                              m=int(round((expected % 1) * 60)), late=late),
                            att, minutes=late)
                day += timedelta(days=1)

        if to_create:
            Issue.create(to_create)
        self.message_post(body=_('Detección ejecutada: %s problemas nuevos.') % len(to_create))
        return True

    def action_view_issues(self):
        """Abre los problemas de esta revisión en la pantalla con filtros y
        acciones masivas."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Problemas — %s') % self.name,
            'res_model': 'zk.attendance.issue',
            'view_mode': 'list,form',
            'search_view_id': self.env.ref('idtx_hr_biometric_zk.zk_issue_search_view').id,
            'domain': [('review_id', '=', self.id)],
            'context': {'search_default_pending': 1, 'search_default_g_type': 1},
        }


class ZkAttendanceIssue(models.Model):
    _name = 'zk.attendance.issue'
    _description = 'Problema de marcación detectado'
    _inherit = ['mail.thread']
    _order = 'date, employee_id'
    _rec_name = 'display_name'

    review_id = fields.Many2one('zk.attendance.review', string='Revisión',
                                required=True, ondelete='cascade')
    company_id = fields.Many2one(related='review_id.company_id', store=True)
    employee_id = fields.Many2one('hr.employee', string='Empleado', required=True, index=True)
    # Nombre capturado (sudo) al detectar: la lista/form lo muestra sin leer
    # hr.employee bajo el usuario, evitando el bloqueo multi-compañía cuando
    # RRHH revisa una empresa que no tiene activa en el selector.
    employee_name = fields.Char(string='Empleado', readonly=True)
    date = fields.Date(string='Día', required=True)
    issue_type = fields.Selection([
        ('double_in', 'Doble ingreso'),
        ('double_out', 'Doble salida'),
        ('single_punch', 'Marca única'),
        ('absence', 'Falta injustificada'),
        ('late', 'Tardanza'),
    ], string='Problema', required=True)
    description = fields.Char(string='Detalle')
    minutes_late = fields.Float(
        string='Min. tardanza',
        help="Minutos de tardanza a contabilizar en la nómina. La tolerancia "
             "de %d min es un umbral: si se supera se cuenta la tardanza "
             "completa (llegó 6 → 6); con 5 o menos no hay tardanza."
             % LATE_TOLERANCE_MIN)
    attendance_id = fields.Many2one('hr.attendance', string='Asistencia', ondelete='set null')
    punch_ids = fields.Many2many('zk.punch', compute='_compute_punches', string='Marcas del día')
    state = fields.Selection([
        ('pending', 'Pendiente'),
        ('fixed', 'Corregido'),
        ('accepted', 'Se deja como está'),
    ], string='Estado', default='pending', required=True, tracking=True)
    resolution_note = fields.Char(string='Resolución', tracking=True)
    resolved_by_id = fields.Many2one('res.users', string='Resuelto por', readonly=True)
    resolved_date = fields.Datetime(string='Fecha resolución', readonly=True)

    @api.depends('employee_name', 'date', 'issue_type')
    def _compute_display_name(self):
        types = dict(self._fields['issue_type'].selection)
        for rec in self:
            rec.display_name = '%s - %s - %s' % (
                rec.date or '', rec.employee_name or '', types.get(rec.issue_type, ''))

    def _compute_punches(self):
        for rec in self:
            rec.punch_ids = self.env['zk.punch'].search([
                ('employee_id', '=', rec.employee_id.id), ('day', '=', rec.date)])

    def _snapshot(self):
        """Texto con el estado actual de la asistencia (para auditoría)."""
        self.ensure_one()
        att = self.attendance_id or self.env["hr.attendance"].search([
            ('employee_id', '=', self.employee_id.id),
            ('check_in', '>=', str(self.date)),
            ('check_in', '<=', '%s 23:59:59' % self.date)], limit=1)
        if not att:
            return _('sin asistencia')
        tz = pytz.timezone(DEVICE_TZ)
        f = lambda d: d and pytz.UTC.localize(d).astimezone(tz).strftime('%d/%m %H:%M') or '—'
        return _('asistencia %(i)s → %(o)s', i=f(att.check_in), o=f(att.check_out))

    def _resolve(self, state, note):
        for rec in self:
            rec.write({
                'state': state,
                'resolution_note': note,
                'resolved_by_id': self.env.user.id,
                'resolved_date': fields.Datetime.now(),
            })
            rec.message_post(body=note)

    # ------------------------------------------------------------------
    #  Acciones del usuario
    # ------------------------------------------------------------------
    def action_open_attendance(self):
        """Abre (o crea) la asistencia del día para corregirla a mano."""
        self.ensure_one()
        ctx = {}
        att = self.attendance_id
        if not att:
            att = self.env['hr.attendance'].search([
                ('employee_id', '=', self.employee_id.id),
                ('check_in', '>=', str(self.date)),
                ('check_in', '<=', '%s 23:59:59' % self.date)], limit=1)
        if not att:
            tz = pytz.timezone(DEVICE_TZ)
            base = tz.localize(datetime.combine(self.date, datetime.min.time().replace(hour=8)))
            ctx.update({'default_employee_id': self.employee_id.id,
                        'default_check_in': base.astimezone(pytz.UTC).replace(tzinfo=None)})
        else:
            self.attendance_id = att
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'hr.attendance',
            'res_id': att.id if att else False,
            'view_mode': 'form',
            'target': 'new',
            'context': ctx,
        }

    def action_mark_fixed(self):
        for rec in self:
            rec._resolve('fixed', _('Corregido manualmente por %(u)s: %(s)s',
                                    u=self.env.user.name, s=rec._snapshot()))
        return True

    def action_accept(self):
        for rec in self:
            rec._resolve('accepted', _('%(u)s decidió dejarlo como está (%(s)s).',
                                       u=self.env.user.name, s=rec._snapshot()))
        return True

    def action_reopen(self):
        return self.write({'state': 'pending', 'resolution_note': False,
                           'resolved_by_id': False, 'resolved_date': False})

    def action_create_leave(self):
        """Para faltas: registrar una ausencia justificada del día."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'hr.leave',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_employee_id': self.employee_id.id,
                'default_request_date_from': self.date,
                'default_request_date_to': self.date,
            },
        }
