# -*- coding: utf-8 -*-
from odoo import models, fields, api

# Reglas de turno (hora local, float):
NIGHT_ENTRY_CUT = 14.0    # ingreso a esta hora o después => turno NOCHE (obrero)
OBRERO_DAY_START = 7.0     # obrero turno día 07:00 -> 19:00
OBRERO_NIGHT_START = 19.0  # obrero turno noche 19:00 -> 07:00
ADMIN_DEFAULT_START = 8.0  # fallback administrativo si no hay calendario


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    l10n_pe_shift_mode = fields.Selection([
        ('obrero', 'Obrero (12h rotativo día/noche)'),
        ('admin', 'Administrativo (solo día)'),
    ], string='Modo de Turno (asistencia)', default='obrero',
        help="Obrero: jornada de 12h que rota entre día (07:00→19:00) y noche "
             "(19:00→07:00); el turno de cada día se deduce de la hora de "
             "ingreso. Administrativo: siempre de día, con la hora de ingreso "
             "de su horario (08:00/08:30); nunca trabaja de noche.")

    def _attendance_shift_for(self, check_in_local, day=None):
        """Devuelve (turno, hora_esperada_float) para una entrada local dada.
        turno = 'day' | 'night'. hora_esperada = hora de ingreso programada
        (float local) para medir tardanza, o None si no aplica."""
        self.ensure_one()
        hour = check_in_local.hour + check_in_local.minute / 60.0
        if self.l10n_pe_shift_mode == 'admin':
            return 'day', self._admin_expected_start(day or check_in_local.date())
        # obrero: el turno se deduce de la hora de ingreso
        if hour >= NIGHT_ENTRY_CUT:
            return 'night', OBRERO_NIGHT_START
        return 'day', OBRERO_DAY_START

    def _admin_expected_start(self, day):
        """Hora de ingreso del administrativo según su calendario (línea de
        mañana del día); fallback 08:00. None si ese día no es laborable."""
        self.ensure_one()
        cal = self.resource_calendar_id
        if not cal or getattr(cal, 'flexible_hours', False):
            return ADMIN_DEFAULT_START
        lines = cal.attendance_ids.filtered(
            lambda a: a.dayofweek == str(day.weekday()) and a.day_period != 'lunch'
            and a.hour_from >= 4.0)  # descarta líneas de madrugada de calendarios rotativos
        if not lines:
            return None
        return min(lines.mapped('hour_from'))
