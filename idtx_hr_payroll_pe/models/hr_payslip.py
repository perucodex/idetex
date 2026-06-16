from odoo import models, fields, api
from odoo.exceptions import ValidationError
from datetime import datetime, timedelta, time, date
import pytz


class HrPayslip(models.Model):
    _inherit = 'hr.payslip'

    def action_print_payslip(self):
        """El botón 'Imprimir' del recibo genera la boleta en formato FULL PIMA
        (reporte propio, sin logo) en vez del recibo estándar de Odoo."""
        if self.filtered('error_count'):
            raise ValidationError(self._get_error_message())
        return self.env.ref(
            'idtx_hr_payroll_pe.action_report_payslip_pe'
        ).report_action(self)

    def _get_payslip_line_total(self, amount, quantity, rate, rule):
        """Redondea el total de CADA línea al céntimo ANTES de acumularlo en las
        categorías. Odoo (base) acumula amount*qty*rate/100 SIN redondear, así
        que GROSS/NET (que se calculan desde las categorías) terminan siendo el
        'redondeo de la suma' mientras que las líneas mostradas son la 'suma de
        redondeos' → descuadre de 1 céntimo entre Total Ingresos y Neto. Al
        redondear aquí, GROSS/NET = suma exacta de las líneas visibles y la
        boleta cuadra (Ingresos − Descuentos = Neto)."""
        total = super()._get_payslip_line_total(amount, quantity, rate, rule)
        currency = self.company_id.currency_id or self.env.company.currency_id
        return currency.round(total) if currency else round(total, 2)

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

        rmv = self._rule_parameter('l10n_pe_rmv') or 0.0
        # Política de horas extra (configurable por parámetro con vigencia):
        #   l10n_pe_he_max_dia   -> tope de HE por día (hoy 3)
        #   l10n_pe_he_grace_min -> tolerancia en minutos para completar la hora
        he_max_dia = int(self._rule_parameter('l10n_pe_he_max_dia') or 3)
        _grace = self._rule_parameter('l10n_pe_he_grace_min')
        he_grace_min = 15.0 if _grace is None else float(_grace)
        # Tolerancia de tardanza en minutos (por día).
        _tol = self._rule_parameter('l10n_pe_tardanza_tolerancia_min')
        tardanza_tol_min = 5.0 if _tol is None else float(_tol)

        # Validación mínima
        if not version or not version.resource_calendar_id:
            return {
                'dias_laborables': 0,
                'dias_trabajados': 0,
                'faltas': 0,
                'domingos_trabajados': 0,
                'noche_horas': 0.0,
                'tardanza_horas': 0.0,
                'he25': 0.0,
                'he35': 0.0,
                'dias_nocturnos': 0,
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
        domingos_trabajados = 0   # domingos con marcación (se pagan al doble)
        tardanza_horas = 0.0
        he25 = 0.0
        he35 = 0.0
        noche_dias = 0           # días calendario programados NOCHE (para nocturna)
        total_horas_jornada = 0.0

        # Horarios de turno (parámetros). La salida de noche > 24 indica que cae
        # al día siguiente (28 = 04:00). El turno de cada día lo define la
        # Programación de Turnos del supervisor, no el calendario.
        dia_ini = self._rule_parameter('l10n_pe_turno_dia_ini')
        dia_ini = 7.0 if dia_ini is None else float(dia_ini)
        dia_fin = self._rule_parameter('l10n_pe_turno_dia_fin')
        dia_fin = 16.0 if dia_fin is None else float(dia_fin)
        noc_ini = self._rule_parameter('l10n_pe_turno_noche_ini')
        noc_ini = 19.0 if noc_ini is None else float(noc_ini)
        noc_fin = self._rule_parameter('l10n_pe_turno_noche_fin')
        noc_fin = 28.0 if noc_fin is None else float(noc_fin)
        # Umbral de hora local para clasificar el turno por la MARCACIÓN: si la
        # entrada (check_in) ocurre a esta hora o después, el día es turno NOCHE;
        # antes, es turno DÍA. Punto medio entre el inicio de día y el de noche.
        noche_threshold = (dia_ini + noc_ini) / 2.0

        def _local(d, hours):
            # Datetime local desde la fecha d + horas (puede pasar de 24 -> día sgte).
            return local_tz.localize(datetime.combine(d, time.min) + timedelta(hours=hours))

        def _to_utc(dt_local):
            return dt_local.astimezone(utc).replace(tzinfo=None)

        # Días laborables por semana del calendario (Lun-Sáb = 6) para convertir
        # semanas de noche a días de bonificación (1 semana de noche -> 7.5 días).
        dias_lab_sem = len(set(
            a.dayofweek for a in calendar.attendance_ids if a.day_period != 'lunch')) or 6

        # Rango ACTIVO del contrato dentro del período (para no contar como falta
        # días previos al ingreso o posteriores al cese).
        ini_activo = max(version.contract_date_start or self.date_from, self.date_from)
        fin_activo = self.date_to
        if version.contract_date_end and version.contract_date_end < fin_activo:
            fin_activo = version.contract_date_end

        # Días cubiertos por una ausencia registrada (vacaciones, licencias,
        # permisos): NO son inasistencias aunque no haya marcación; los manejan
        # las reglas VACA/LICGOCE (pagadas) o FALTA por work entries (no pagadas).
        leave_days = set()
        leaves = self.env['hr.leave'].sudo().search([
            ('employee_id', '=', employee.id),
            ('state', '=', 'validate'),
            ('request_date_from', '<=', self.date_to),
            ('request_date_to', '>=', self.date_from),
        ])
        for lv in leaves:
            d = lv.request_date_from
            while d and lv.request_date_to and d <= lv.request_date_to:
                leave_days.add(d)
                d += timedelta(days=1)

        # Feriados (días festivos) configurados en Tiempo Personal como "Días
        # Festivos" (resource.calendar.leaves SIN recurso): tampoco son
        # inasistencias; el día está pagado (incluido en el sueldo mensual de 30).
        holidays = self.env['resource.calendar.leaves'].sudo().search([
            ('resource_id', '=', False),
            ('date_from', '<=', _to_utc(_local(self.date_to, 24))),
            ('date_to', '>=', _to_utc(_local(self.date_from, 0))),
            '|', ('calendar_id', '=', False), ('calendar_id', '=', calendar.id),
            '|', ('company_id', '=', False), ('company_id', '=', self.company_id.id),
        ])
        for h in holidays:
            hd = utc.localize(h.date_from).astimezone(local_tz).date()
            hend = utc.localize(h.date_to).astimezone(local_tz).date()
            while hd <= hend:
                leave_days.add(hd)
                hd += timedelta(days=1)

        current = self.date_from
        end = self.date_to

        while current <= end:
            # DOMINGO = descanso semanal. Nunca es día laborable ni falta. Si hay
            # marcación ese domingo, se paga el dominical al DOBLE (jornal × 2).
            if current.weekday() == 6:
                if ini_activo <= current <= fin_activo:
                    sun_start = _to_utc(_local(current, 0))
                    sun_end = _to_utc(_local(current, 24))
                    if self.env['hr.attendance'].sudo().search_count([
                        ('employee_id', '=', employee.id),
                        ('check_in', '>=', sun_start),
                        ('check_in', '<', sun_end),
                    ]):
                        domingos_trabajados += 1
                current += timedelta(days=1)
                continue

            # ¿Día laborable? Lo define el horario de trabajo (qué días se trabaja).
            day_atts = calendar.attendance_ids.filtered(
                lambda a: int(a.dayofweek) == current.weekday() and a.day_period != 'lunch'
            )
            if not day_atts:
                current += timedelta(days=1)
                continue

            dias_laborables += 1
            total_horas_jornada += 8.0

            # Asistencia del día: primera marca cuyo check_in cae dentro del día
            # local. El TURNO se deriva de la marcación (no de una programación).
            day_start_utc = _to_utc(_local(current, 0))
            day_end_utc = _to_utc(_local(current, 24))
            attendance = self.env['hr.attendance'].sudo().search([
                ('employee_id', '=', employee.id),
                ('check_in', '>=', day_start_utc),
                ('check_in', '<', day_end_utc),
            ], order='check_in', limit=1)

            if not attendance:
                # Inasistencia (falta injustificada) solo si: el día está dentro
                # del rango activo del contrato y NO está cubierto por una ausencia
                # registrada (vacaciones/licencia/permiso). El domingo ya se maneja
                # arriba (nunca llega acá).
                if ini_activo <= current <= fin_activo and current not in leave_days:
                    faltas += 1
                current += timedelta(days=1)
                continue

            dias_trabajados += 1

            # TURNO derivado de la MARCACIÓN: si la entrada (hora local) es a partir
            # del umbral, es turno NOCHE; si es antes, turno DÍA. Esto fija las horas
            # de referencia para tardanza/HE y cuenta los días de nocturna.
            ci_hour = utc.localize(attendance.check_in).astimezone(local_tz).hour
            shift = 'noche' if ci_hour >= noche_threshold else 'dia'
            if shift == 'noche':
                noche_dias += 1   # días LABORABLES trabajados de noche (semana = dias_lab_sem)

            # Horas de entrada/salida según el turno detectado.
            if shift == 'noche':
                sched_in_local = _local(current, noc_ini)
                sched_out_local = _local(current, noc_fin)   # noc_fin > 24 => día sgte
            else:
                sched_in_local = _local(current, dia_ini)
                sched_out_local = _local(current, dia_fin)
            sched_in_utc = _to_utc(sched_in_local)
            sched_out_utc = _to_utc(sched_out_local)

            # TARDANZA: minutos ENTEROS de retraso; se descuentan solo si superan
            # la tolerancia (param). Ej. tol=5: 07:05 (5 min) no descuenta;
            # 07:06 (6 min) descuenta 6 min. Las fracciones de minuto no cuentan.
            if attendance.check_in > sched_in_utc:
                late_min = int((attendance.check_in - sched_in_utc).total_seconds() // 60)
                if late_min > tardanza_tol_min:
                    tardanza_horas += late_min / 60.0

            # HORAS EXTRA: bloques de hora COMPLETA sobre la SALIDA PROGRAMADA del
            # turno (incluido el cruce de medianoche en el turno noche). Tolerancia
            # (grace) y tope diario configurables; la entrada anticipada no cuenta.
            if attendance.check_out and attendance.check_out > sched_out_utc:
                extra_min = (attendance.check_out - sched_out_utc).total_seconds() / 60.0
                he_dia = int((extra_min + he_grace_min) // 60)
                if he_dia > he_max_dia:
                    he_dia = he_max_dia
                if he_dia > 0:
                    # Regla legal: las primeras 2h de OT del día al 25%, de la
                    # 3ª hora en adelante al 35%. (7 a 7 = jornada 8h hasta 16:00
                    # + 3h de OT hasta 19:00 -> 2h@25% + 1h@35%.) El 50% del 25%
                    # se reclasifica luego a Condición de Trabajo (regla CONDTRAB_PE).
                    h25 = min(he_dia, 2)
                    he25 += h25
                    he35 += (he_dia - h25)

            current += timedelta(days=1)

        # Bonificación nocturna POR HORAS (no por días): cada día de nocturna
        # equivale a 8h; el factor 7.5/dias_lab_sem incluye el descanso semanal
        # proporcional (1 sem de noche = 6 lab -> 7.5 días -> 60h). NO se trunca
        # (en horas). Tope mes comercial = 30 días = 240h.
        dias_nocturnos = min(int(noche_dias / dias_lab_sem * 7.5), 30) if dias_lab_sem else 0
        noche_horas = round(min(noche_dias / dias_lab_sem * 7.5, 30.0) * 8.0, 2) if dias_lab_sem else 0.0
        horas_promedio = (
            total_horas_jornada / dias_laborables
            if dias_laborables else 8.0
        )

        return {
            'rmv': rmv,
            'dias_laborables': dias_laborables,
            'dias_trabajados': dias_trabajados,
            'faltas': faltas,
            'domingos_trabajados': domingos_trabajados,
            'tardanza_horas': round(tardanza_horas, 4),
            'he25': round(he25, 4),
            'he35': round(he35, 4),
            'dias_nocturnos': dias_nocturnos,
            'noche_horas': noche_horas,
            'horas_jornada': round(horas_promedio, 2),
        }

    # ==========================================================
    #  LOCALDICT → DISPONIBLE EN REGLAS SALARIALES
    # ==========================================================
    def _get_localdict(self):
        localdict = super()._get_localdict()
        localdict.update(self._pe_compute_attendance_data())
        # Exponer la lectura de parámetros legales con vigencia a las reglas:
        #   rule_parameter('l10n_pe_rmv')         -> valor vigente a date_to
        #   rule_parameter('l10n_pe_uit', fecha)  -> valor vigente a 'fecha'
        # Evita hardcodear RMV/UIT/RMA/tasas/tramos de 5ta en las reglas.
        localdict['rule_parameter'] = self._rule_parameter
        # Retención de renta de 5ta categoría (procedimiento SUNAT).
        localdict['pe_5ta_retencion'] = self._pe_compute_5ta_retencion
        # Remuneración computable (base de gratificación / CTS / vacaciones).
        localdict['pe_rem_computable'] = self._pe_remuneracion_computable
        # Remuneración computable VACACIONAL = básico + asig. familiar + promedio
        # de los últimos 6 meses de HE 25/35, prima textil y bonif. nocturna.
        localdict['pe_rem_vacacional'] = self._pe_rem_vacacional
        # Factor de beneficios sociales según régimen (general 1, pequeña 0.5, micro 0).
        localdict['pe_benefit_factor'] = self._pe_benefit_factor
        # Tasa de EsSalud según régimen (general/agrario), 0 si micro (usa SIS).
        localdict['pe_essalud_rate'] = self._pe_essalud_rate
        # Crédito EPS aplicable contra el aporte a EsSalud.
        localdict['pe_eps_credit'] = self._pe_eps_credit
        # Prestación alimentaria automática (monto si cumple antigüedad mínima).
        localdict['pe_prestacion_alimentaria'] = self._pe_prestacion_alimentaria
        return localdict

    def _pe_prestacion_alimentaria(self):
        """Monto AUTOMÁTICO de prestación alimentaria (vales) para trabajadores
        con la antigüedad mínima configurada a la fecha del recibo.

        Parámetros (con vigencia):
          - l10n_pe_pres_alim_monto  -> monto (p. ej. 200)
          - l10n_pe_pres_alim_meses  -> antigüedad mínima en meses cumplidos
        Devuelve 0 si no cumple. El input manual PRES_ALIM (si se carga) lo maneja
        la regla y tiene prioridad sobre este automático.
        """
        self.ensure_one()
        monto = self._rule_parameter('l10n_pe_pres_alim_monto') or 0.0
        meses_min = self._rule_parameter('l10n_pe_pres_alim_meses') or 0
        start = self.version_id.contract_date_start
        if not start or not self.date_to or monto <= 0:
            return 0.0
        meses = (self.date_to.year - start.year) * 12 + (self.date_to.month - start.month)
        if self.date_to.day < start.day:
            meses -= 1
        return monto if meses >= meses_min else 0.0

    def _pe_rem_vacacional(self):
        """Remuneración computable VACACIONAL (mensual) =
        SUELDO BÁSICO FIJO (version.wage, NO se promedia) + PROMEDIO de los
        últimos 6 meses (los que existan) de las variables:
        HE 25% + HE 35% + BONIF. NOCTURNA + PRIMA TEXTIL.
        (No incluye asignación familiar.) La regla VACA_PE paga
        pe_rem_vacacional() / 30 * días de vacaciones. En el mes más antiguo
        (sin 6 meses previos) la vacacional se carga manual vía el input VAC_DIARIO.
        """
        self.ensure_one()
        base = self.version_id.wage or 0.0            # sueldo fijo, NO promediado
        if not self.date_from:
            return base
        codes = ('HE25_PE', 'HE35_PE', 'NOCT_PE', 'PRIMTEX_PE')   # solo variables
        y, m = self.date_from.year, self.date_from.month
        total, n = 0.0, 0
        for k in range(1, 7):                       # 6 meses anteriores
            mm, yy = m - k, y
            while mm <= 0:
                mm += 12
                yy -= 1
            start = date(yy, mm, 1)
            end = (date(yy, mm + 1, 1) - timedelta(days=1)) if mm < 12 else date(yy, 12, 31)
            lines = self.env['hr.payslip.line'].sudo().search([
                ('slip_id.employee_id', '=', self.employee_id.id),
                ('slip_id.state', '!=', 'cancel'),
                ('code', 'in', codes),
                ('slip_id.date_from', '>=', start),
                ('slip_id.date_to', '<=', end),
            ])
            if lines:
                n += 1
                total += sum(lines.mapped('total'))
            else:
                seed = self._pe_vacacional_seed_for_period(start, end)
                if seed is not None:
                    n += 1
                    total += seed
        return base + (total / n if n else 0.0)

    def _pe_vacacional_seed_for_period(self, start, end):
        """Hook (extensible): monto MENSUAL de variables (HE25+HE35+nocturna+
        prima) para un mes de la ventana de 6 que NO tiene boleta en el sistema
        (meses anteriores al go-live). El core NO siembra nada (devuelve None).
        El módulo opcional `idtx_hr_vacacional_seed_pe` lo sobreescribe para leer
        el histórico cargado a mano por mes; ese módulo se puede desinstalar una
        vez que ya existen 6 boletas reales y el seed deja de usarse.
        Devolver None = no hay seed para ese mes (no se cuenta en el promedio).
        """
        self.ensure_one()
        return None

    def _pe_eps_credit(self, base):
        """Crédito EPS contra el aporte a EsSalud, para trabajadores afiliados a
        una EPS: 25% del aporte a EsSalud, con tope de 10% de la UIT por
        trabajador. El empleador sigue pagando el 9%, pero ese crédito se destina
        a la EPS en lugar de a EsSalud.
        """
        self.ensure_one()
        if not self.employee_id.l10n_pe_has_eps:
            return 0.0
        rate = self._pe_essalud_rate()
        if rate <= 0:
            return 0.0
        credit = base * rate * 0.25
        uit = self._rule_parameter('l10n_pe_uit') or 0.0
        cap = 0.10 * uit
        if cap and credit > cap:
            credit = cap
        return credit

    def _pe_benefit_factor(self):
        """Factor aplicable a gratificación / CTS / vacaciones según el régimen
        laboral del contrato:
          - General / Textil / Agrario (Ley 31110): 1.0 (beneficios completos).
          - MYPE Pequeña: 0.5 (½ gratificación, ½ CTS, 15 días de vacaciones).
          - MYPE Micro: 0.0 (sin gratificación ni CTS).
        """
        self.ensure_one()
        regime = self.version_id.l10n_pe_labor_regime
        if regime == 'mype_micro':
            return 0.0
        if regime == 'mype_pequena':
            return 0.5
        return 1.0

    def _pe_essalud_rate(self):
        """Tasa de EsSalud (aporte del empleador) según régimen:
          - Agrario (Ley 31110): tasa diferenciada en transición (param).
          - MYPE Micro: 0 (usa SIS, no EsSalud).
          - Resto: 9% (param general).
        """
        self.ensure_one()
        regime = self.version_id.l10n_pe_labor_regime
        if regime == 'agrario':
            return self._rule_parameter('l10n_pe_essalud_agrario_rate') or 0.09
        if regime == 'mype_micro':
            return 0.0
        return self._rule_parameter('l10n_pe_essalud_rate') or 0.09

    def _pe_remuneracion_computable(self):
        """Remuneración computable mensual (régimen general): remuneración
        regular = sueldo básico + asignación familiar. Base de gratificación,
        CTS y vacaciones.

        NOTA: el promedio de remuneraciones variables/regulares (horas extra,
        comisiones percibidas al menos 3 meses en el semestre) se integrará como
        refinamiento; por ahora toma la remuneración fija mensual.
        """
        self.ensure_one()
        rem = self.version_id.wage or 0.0
        if self.employee_id.l10n_pe_family_allowance_right:
            rmv = self._rule_parameter('l10n_pe_rmv') or 0.0
            pct = self._rule_parameter('l10n_pe_asig_fam_pct') or 0.10
            rem += rmv * pct
        return rem

    # ==========================================================
    #  RENTA DE 5ta CATEGORÍA  (art. 40 Reglamento del IR)
    # ==========================================================
    def _pe_compute_5ta_retencion(self):
        """Retención mensual de renta de 5ta categoría (procedimiento SUNAT),
        usando parámetros con vigencia (UIT, deducción 7 UIT, tramos).

        Proyección estándar: remuneración regular mensual (sueldo + asignación
        familiar) por los meses que faltan del ejercicio (incl. el actual) +
        remuneraciones ya percibidas en el año + 2 gratificaciones. Renta neta =
        proyección − 7 UIT; impuesto anual = tramos progresivos; la retención del
        mes aplica los divisores del art. 40 y la regularización en diciembre.

        Devuelve la retención del mes (>= 0); el signo de descuento lo pone la
        regla salarial.
        """
        self.ensure_one()
        if not self.date_to:
            return 0.0
        version = self.version_id
        employee = self.employee_id
        year = self.date_to.year
        month = self.date_to.month

        uit = self._rule_parameter('l10n_pe_uit') or 0.0
        ded_uit = self._rule_parameter('l10n_pe_5ta_deduccion_uit') or 7.0
        tramos = self._rule_parameter('l10n_pe_5ta_tramos') or []
        if not uit or not tramos:
            return 0.0

        # Base mensual afecta a 5ta. Si el trabajador tiene "sueldo pactado"
        # (neto), la 5ta se calcula sobre ese pactado; si no, sobre la
        # remuneración regular (sueldo + asignación familiar) y solo aplica si la
        # proyección supera las 7 UIT.
        pactado = version.l10n_pe_sueldo_pactado or 0.0
        if pactado > 0:
            rem_mes = pactado
        else:
            rem_mes = version.wage or 0.0
            if employee.l10n_pe_family_allowance_right:
                rmv = self._rule_parameter('l10n_pe_rmv') or 0.0
                asig_pct = self._rule_parameter('l10n_pe_asig_fam_pct') or 0.10
                rem_mes += rmv * asig_pct
        if rem_mes <= 0:
            return 0.0

        def _last_day(y, m):
            return (date(y, 12, 31) if m == 12
                    else date(y, m + 1, 1) - timedelta(days=1))

        jan1 = date(year, 1, 1)
        meses_restantes = 13 - month                  # mes actual .. diciembre
        gratis = 2.0 * rem_mes                         # gratificaciones jul + dic

        if pactado > 0:
            # Proyección de año completo sobre el pactado (base mensual estable).
            rba = rem_mes * 12.0 + gratis
        else:
            # Remuneraciones afectas ya percibidas en meses anteriores del año.
            prior_rem = self._sum('GROSS', jan1, _last_day(year, month - 1)) if month > 1 else 0.0
            rba = rem_mes * meses_restantes + prior_rem + gratis  # bruta anual proy.
        rna = rba - ded_uit * uit                      # renta neta anual
        if rna <= 0:
            return 0.0

        # Impuesto anual proyectado (tramos progresivos en UIT).
        ia = 0.0
        prev_limit = 0.0
        for limit_uit, rate in tramos:
            limit_soles = limit_uit * uit
            tramo_base = min(rna, limit_soles) - prev_limit
            if tramo_base > 0:
                ia += tramo_base * rate
            if rna <= limit_soles:
                break
            prev_limit = limit_soles

        # Retenciones de 5ta ya efectuadas en el año hasta el cierre del bloque
        # anterior (las líneas RENTA5TA son negativas → se invierte el signo).
        def _ret_acum(to_month):
            if to_month < 1:
                return 0.0
            return -self._sum('RENTA5TA', jan1, _last_day(year, to_month))

        if month in (1, 2, 3):
            ret = ia / 12.0
        elif month == 4:
            ret = (ia - _ret_acum(3)) / 9.0
        elif month in (5, 6, 7):
            ret = (ia - _ret_acum(4)) / 8.0
        elif month == 8:
            ret = (ia - _ret_acum(7)) / 5.0
        elif month in (9, 10, 11):
            ret = (ia - _ret_acum(8)) / 4.0
        else:  # diciembre: regularización
            ret = ia - _ret_acum(11)

        return max(ret, 0.0)
