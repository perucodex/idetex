from odoo import models, fields, api
from datetime import datetime, timedelta, time
import pytz


class HrPayslip(models.Model):
    _inherit = 'hr.payslip'

    # ==========================================================
    #  DATA CENTRALIZADA DE ASISTENCIAS – PERÚ (ODOO 19)
    # ==========================================================
    def _pe_compute_attendance_data(self):
        """
        Calcula:
        - días laborables (según calendario, sin lunch)
        - días trabajados reales
        - faltas
        - tardanzas (horas)
        - horas extra 25% y 35%
        - horas promedio de jornada (8h / 12h / etc.)
        """

        self.ensure_one()
        employee = self.employee_id
        version = self.version_id

        rmv = float(self.env['ir.config_parameter'].sudo().get_param('idtx_hr_payroll_pe.minimum_living_wage', 0))

        # Validación mínima
        if not version or not version.resource_calendar_id:
            return {
                'dias_laborables': 0,
                'dias_trabajados': 0,
                'faltas': 0,
                'tardanza_horas': 0.0,
                'he25': 0.0,
                'he35': 0.0,
                'horas_jornada': 8.0,
            }

        calendar = version.resource_calendar_id

        # ZONA HORARIA (PERÚ)
        tz_name = (
            calendar.tz
            or employee.tz
            or self.company_id.resource_calendar_id.tz
            or 'UTC'
        )
        local_tz = pytz.timezone(tz_name)
        utc = pytz.UTC

        dias_laborables = 0
        dias_trabajados = 0
        faltas = 0
        tardanza_horas = 0.0
        he25 = 0.0
        he35 = 0.0
        total_horas_jornada = 0.0

        current = self.date_from
        end = self.date_to

        while current <= end:

            # Tramos del día (SIN LUNCH)
            attendances_today = calendar.attendance_ids.filtered(
                lambda a:
                    int(a.dayofweek) == current.weekday()
                    and a.day_period != 'lunch'
            )

            if not attendances_today:
                current += timedelta(days=1)
                continue

            dias_laborables += 1

            # Horas teóricas del día
            horas_jornada_dia = sum(
                a.hour_to - a.hour_from for a in attendances_today
            )
            total_horas_jornada += horas_jornada_dia

            # Hora teórica de ingreso y salida (local → UTC)
            hora_in_prog = min(a.hour_from for a in attendances_today)
            hora_out_prog = max(a.hour_to for a in attendances_today)

            hora_in_local = local_tz.localize(
                datetime.combine(current, time.min) + timedelta(hours=hora_in_prog)
            )
            hora_out_local = local_tz.localize(
                datetime.combine(current, time.min) + timedelta(hours=hora_out_prog)
            )

            hora_in_utc = hora_in_local.astimezone(utc).replace(tzinfo=None)
            hora_out_utc = hora_out_local.astimezone(utc).replace(tzinfo=None)

            # Asistencia real (UTC)
            attendance = self.env['hr.attendance'].sudo().search([
                ('employee_id', '=', employee.id),
                ('check_in', '>=', hora_in_utc - timedelta(hours=4)),
                ('check_in', '<=', hora_out_utc + timedelta(hours=4)),
            ], limit=1)

            # INASISTENCIA
            if not attendance:
                faltas += 1
                current += timedelta(days=1)
                continue

            dias_trabajados += 1

            # TARDANZA
            if attendance.check_in > hora_in_utc:
                diff = (attendance.check_in - hora_in_utc).total_seconds()
                tardanza_horas += diff / 3600.0

            # HORAS EXTRA
            # if attendance.check_out and attendance.check_out > hora_out_utc:
                # diff_out = (attendance.check_out - hora_out_utc).total_seconds()
                # horas_extra = diff_out / 3600.0
            if attendance.validated_overtime_hours:
                horas_extra = attendance.validated_overtime_hours
                if horas_extra <= 2:
                    he25 += horas_extra
                else:
                    he25 += 2
                    he35 += (horas_extra - 2)

            current += timedelta(days=1)

        horas_promedio = (
            total_horas_jornada / dias_laborables
            if dias_laborables else 8.0
        )

        return {
            'rmv': rmv,
            'dias_laborables': dias_laborables,
            'dias_trabajados': dias_trabajados,
            'faltas': faltas,
            'tardanza_horas': round(tardanza_horas, 4),
            'he25': round(he25, 4),
            'he35': round(he35, 4),
            'horas_jornada': round(horas_promedio, 2),
        }

    # ==========================================================
    #  LOCALDICT → DISPONIBLE EN REGLAS SALARIALES
    # ==========================================================
    def _get_localdict(self):
        localdict = super()._get_localdict()
        localdict.update(self._pe_compute_attendance_data())
        return localdict
