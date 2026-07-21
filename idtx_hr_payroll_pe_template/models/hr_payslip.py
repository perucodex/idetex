from odoo import models, fields


class HrPayslip(models.Model):
    _inherit = 'hr.payslip'

    # ----------------------------------------------------------
    #  TAREO (Excel) — cantidades cargadas desde el lote de nómina.
    #  Cuando l10n_pe_tareo_loaded=True, los "Días trabajados" se
    #  generan desde estos campos (ver _pe_tareo_worked_day_lines) y el
    #  motor de asistencias devuelve ceros (ver _pe_tareo_attendance_data).
    #  Los bonos/descuentos (HE25/HE35/nocturna/tardanza/condición/comedor/
    #  adelanto/otros) entran como input_line_ids (Entradas salariales).
    # ----------------------------------------------------------
    l10n_pe_tareo_loaded = fields.Boolean(
        string='Cargado desde Tareo', copy=False,
        help="La boleta fue poblada desde el Excel de tareo del lote.")
    l10n_pe_tareo_horas_noct = fields.Float(string='Tareo: Horas nocturnas', copy=False)
    l10n_pe_tareo_faltas = fields.Float(string='Tareo: Faltas (días)', copy=False)
    l10n_pe_tareo_vac = fields.Float(string='Tareo: Vacaciones (días)', copy=False)
    l10n_pe_tareo_lic_cg = fields.Float(string='Tareo: Licencia c/goce (días)', copy=False)

    # ==========================================================
    #  MODO TAREO (EXCEL) — SUSTITUYE A LAS MARCACIONES
    # ==========================================================
    def _pe_tareo_dias_asistencia(self):
        """Días efectivos de asistencia en modo tareo. Premisa: todos trabajan
        el mes comercial de 30 días; las faltas/tardanzas se descuentan aparte
        (FALTA_PE / TARD_PE). Asistencia = 30 − faltas − vacaciones − licencia
        c/goce (estas dos se pagan en líneas propias)."""
        self.ensure_one()
        dias = 30.0 - (self.l10n_pe_tareo_faltas or 0.0) \
            - (self.l10n_pe_tareo_vac or 0.0) - (self.l10n_pe_tareo_lic_cg or 0.0)
        return max(dias, 0.0)

    def _pe_tareo_attendance_data(self):
        """Datos de asistencia en 'modo tareo': el motor NO lee marcaciones.
        Devuelve ceros para he25/he35/faltas/tardanza/nocturna/domingos (esos
        conceptos entran por inputs cargados del tareo, o no aplican). La jornada
        (para el valor-hora de HE) sale del calendario del contrato o 8h."""
        self.ensure_one()
        rmv = self._rule_parameter('l10n_pe_rmv') or 0.0
        cal = self.version_id.resource_calendar_id
        horas_jornada = (cal.hours_per_day if cal and cal.hours_per_day else 8.0)
        return {
            'rmv': rmv,
            'dias_laborables': 0,
            'dias_trabajados': self._pe_tareo_dias_asistencia(),
            'faltas': 0.0,
            'domingos_trabajados': 0.0,
            'tardanza_horas': 0.0,
            'he25': 0.0,
            'he35': 0.0,
            'dias_nocturnos': 0,
            'noche_horas': 0.0,
            'horas_jornada': round(horas_jornada, 2),
        }

    def _pe_tareo_worked_day_lines(self):
        """Líneas de 'Días trabajados' desde el tareo (lista de dicts, igual
        formato que _get_worked_day_lines):
          - Asistencia (WORK100): días trabajados, horas = diurnas + nocturnas.
          - Falta Injustificada (FALTA_INJ, no pagada) → alimenta FALTA_PE.
          - Vacaciones (VAC) y Licencia c/Goce (LIC_CG) si el tareo las trae
            (SUELDO_PE las descuenta de los días y VACA_PE/LICGOCE_PE las pagan).
        """
        self.ensure_one()
        hpd = self._get_worked_day_lines_hours_per_day() or 8.0
        att = self.env.ref('hr_work_entry.work_entry_type_attendance')
        dias_asist = self._pe_tareo_dias_asistencia()
        # Horas de la Asistencia = días × jornada (informativo). Las horas
        # nocturnas NO se suman aquí: alimentan la bonificación nocturna vía
        # el input HORAS_NOCT.
        lines = [{
            'sequence': att.sequence,
            'work_entry_type_id': att.id,
            'number_of_days': dias_asist,
            'number_of_hours': dias_asist * hpd,
        }]
        for xmlid, days in (
            ('idtx_hr_payroll_pe.we_falta_injustificada', self.l10n_pe_tareo_faltas or 0.0),
            ('idtx_hr_payroll_pe.work_entry_type_vac', self.l10n_pe_tareo_vac or 0.0),
            ('idtx_hr_payroll_pe.we_licencia_con_goce', self.l10n_pe_tareo_lic_cg or 0.0),
        ):
            if days:
                wet = self.env.ref(xmlid)
                lines.append({
                    'sequence': wet.sequence,
                    'work_entry_type_id': wet.id,
                    'number_of_days': days,
                    'number_of_hours': days * hpd,
                })
        return lines

    # ==========================================================
    #  Overrides: enganchan el modo tareo al cálculo del base
    # ==========================================================
    def _pe_compute_attendance_data(self):
        # En modo TAREO no se leen las marcaciones: los días/horas vienen del
        # Excel de tareo. Si no, el cálculo por asistencias del base.
        self.ensure_one()
        if self.company_id.l10n_pe_use_tareo:
            return self._pe_tareo_attendance_data()
        return super()._pe_compute_attendance_data()

    def _get_worked_day_lines(self, domain=None, check_out_of_version=True):
        # En modo tareo las líneas de días trabajados se generan desde el tareo
        # (sobrevive a recomputaciones); si no, comportamiento estándar.
        self.ensure_one()
        if self.l10n_pe_tareo_loaded:
            return self._pe_tareo_worked_day_lines()
        return super()._get_worked_day_lines(domain=domain, check_out_of_version=check_out_of_version)
