# -*- coding: utf-8 -*-
from odoo import models

# Reglas de turno (hora local, float):
NIGHT_ENTRY_CUT = 14.0    # ingreso a esta hora o después => turno NOCHE (obrero rotativo)
OBRERO_DAY_START = 7.0     # fallback obrero día 07:00 -> 19:00
OBRERO_NIGHT_START = 19.0  # fallback obrero noche 19:00 -> 07:00
DEFAULT_DAY_START = 8.0    # fallback administrativo/empleado sin calendario


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    # El turno rotativo día/noche (12h, cruce de medianoche) es EXCLUSIVO de
    # los OBREROS (employee_type='worker') con horario de 2 semanas (el
    # calendar rotativo). Cualquier otro (empleado/admin) es siempre de día.
    def _is_rotating_worker(self):
        self.ensure_one()
        cal = self.resource_calendar_id
        return self.employee_type == 'worker' and bool(cal) and cal.two_weeks_calendar

    def _cal_start_in_range(self, day, lo, hi):
        """Hora de ingreso (float) programada ese día tomando la línea de
        trabajo (no refrigerio) más temprana con hour_from en [lo, hi). None
        si ese día no es laborable en ese rango."""
        self.ensure_one()
        cal = self.resource_calendar_id
        if not cal or getattr(cal, 'flexible_hours', False):
            return None
        lines = cal.attendance_ids.filtered(
            lambda a: a.dayofweek == str(day.weekday()) and a.day_period != 'lunch'
            and lo <= a.hour_from < hi)
        return min(lines.mapped('hour_from')) if lines else None

    def _is_laborable(self, day):
        """¿Ese día calendario es laborable para el empleado?"""
        self.ensure_one()
        cal = self.resource_calendar_id
        if not cal or getattr(cal, 'flexible_hours', False):
            return True
        return bool(cal.attendance_ids.filtered(
            lambda a: a.dayofweek == str(day.weekday()) and a.day_period != 'lunch'))

    def _attendance_shift_for(self, check_in_local, day=None):
        """Devuelve (turno, hora_esperada_float) para una entrada local.
        turno = 'day' | 'night'. hora_esperada = ingreso programado (float
        local) para medir tardanza, o None si ese día no es laborable.
        Solo los obreros rotativos usan turno noche; el resto siempre día."""
        self.ensure_one()
        day = day or check_in_local.date()
        hour = check_in_local.hour + check_in_local.minute / 60.0
        if self._is_rotating_worker():
            if hour >= NIGHT_ENTRY_CUT:
                return 'night', (self._cal_start_in_range(day, NIGHT_ENTRY_CUT, 24.0) or OBRERO_NIGHT_START)
            return 'day', (self._cal_start_in_range(day, 4.0, NIGHT_ENTRY_CUT) or OBRERO_DAY_START)
        # Empleado/administrativo: siempre día, con la hora de su calendario.
        exp = self._cal_start_in_range(day, 0.0, 24.0)
        if exp is None and self._is_laborable(day):
            exp = DEFAULT_DAY_START
        return 'day', exp
