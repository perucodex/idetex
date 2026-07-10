# -*- coding: utf-8 -*-
import datetime
import logging

from odoo import models, fields, api
import pytz
from .utils import _safe_date, _safe_str, _safe_float

_logger = logging.getLogger(__name__)

# Canonicaliza grafías inconsistentes del área que llegan de TEXPLUS
# (estatus_reproceso.area) o del nombre del workcenter de Odoo. La clave se
# busca normalizada (mayúsculas, espacios colapsados); el valor es la forma
# canónica que usa el resto del módulo (p. ej. FIRST_AREA en control_pedido.py).
# Ej.: 'PRETINTORERIA' (sin espacio, fases ESMCRU*) -> 'PRE TINTORERIA'.
_AREA_CANON = {
    'PRETINTORERIA': 'PRE TINTORERIA',
}

# Zona horaria de la planta. Las fechas de las fases (barFasDTF) se guardan en
# UTC; para fechas de negocio (p. ej. el día de término del acabado) hay que
# convertir a hora local de Perú antes de tomar el día.
_PE_TZ = pytz.timezone('America/Lima')


def _canonical_area(area):
    if not area:
        return area
    key = ' '.join(str(area).split()).upper()
    return _AREA_CANON.get(key, area)


class ControlPedidoLine(models.Model):
    _name = "control.pedido.line"
    _description = "Control Pedido (Detalle)"
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'batch'

    pedido_id = fields.Many2one("control.pedido", required=True, ondelete="cascade")
    customer = fields.Char(related='pedido_id.customer', store=True, readonly=True)
    route = fields.Char(string="Route")
    codpro = fields.Char('Codigo Producto')
    product_id = fields.Many2one('product.template', string='Product')
    description = fields.Char('Articulo')
    barcodreo = fields.Char('Reprocess')
    batch = fields.Char('Batch')
    process = fields.Char(string="Next Process")
    next_process = fields.Char(
        string="Siguiente Proceso",
        compute='_compute_next_process',
        store=True,
        help="Primer proceso de la partida cuyo barFasDTF (fecha fin) este vacio. "
             "Puede tener barFasDTI iniciado pero sin terminar.",
    )
    parent_operation_id = fields.Many2one(
        'mrp.routing.workcenter.operation', string='Fase Padre',
        compute='_compute_parent_operation_id', store=True,
        help="Fase padre de la operación cuyo name coincide con el "
             "'Siguiente Proceso' (next_process). Permite agrupar partidas por "
             "fase padre en el reporte de Kilos por Fase.",
    )
    area = fields.Char('Area')
    rollos = fields.Integer('Rolls')
    kilograms = fields.Float('Kilograms')
    start_date = fields.Datetime('Start Date')
    end_date = fields.Datetime('End Date')
    colorcode = fields.Char('Color Code')
    colorname = fields.Char('Color Name')
    lab_dev_line_id = fields.Many2one('lab.dev.line', string='Lab Dev')
    colorfastness_id = fields.Many2one(related='lab_dev_line_id.colorfastness_washing_id')
    density_stability_twisting_id = fields.Many2one(related='product_id.analysis_id.density_stability_twisting_id')
    proceso_ids = fields.One2many(
        "control.proceso.lines",
        "pedido_line_id",
        string="Procesos"
    )
    # Adicionales para control con sitpro reprocesos
    area_num_days = fields.Integer('Area Num Days', compute='_compute_area_num_days', store=True)
    num_days = fields.Integer('Number of Days', related='pedido_id.num_days', store=True)
    # Filled from SQL Server ctrl_info during sync: motivo/area of the most
    # recent open REPROCESO/REPOSICION record whose `correlvou` matches `batch`.
    report_date = fields.Datetime('Fecha Informe')
    motivo = fields.Char('Motivo')
    obsctrl = fields.Text('Observaciones Informe')
    change_date = fields.Datetime('Fecha Cambio Area', compute='_compute_area_num_days', store=True)
    motivo1 = fields.Char('Motivo Reproceso')
    area1 = fields.Char('Área Responsable')
    to_reprocess = fields.Float('To Reprocess')
    state = fields.Selection([
        ('active', 'Active'),
        ('completed', 'Completed'),
    ], string='State', default='active')
    wish_date = fields.Date('Fecha Deseada',
        help="Fecha objetivo de entrega de esta partida. Hereda del "
             "control.pedido al crearse pero se puede modificar por linea.")

    # ------------------------------------------------------------------
    # Métricas de Acabado (reporte pivot "Kilos de Acabado")
    # El área de cada proceso se deriva: proceso.fas_code/fasCod ->
    # mrp.routing.workcenter.operation -> workcenter.operation_type
    # (acabado='finishing', control de calidad='quality').
    # ------------------------------------------------------------------
    finishing_ops_pending = fields.Integer(
        string='Operaciones de Acabado Pendientes',
        compute='_compute_finishing_metrics', store=True,
        help="Cantidad de operaciones del área de ACABADO aún sin fecha de fin.")
    finishing_ops_group = fields.Char(
        string='Operaciones Acabado',
        compute='_compute_finishing_metrics', store=True,
        help="Etiqueta 'Operaciones N' = nº de operaciones de acabado pendientes. "
             "Vacío si la partida no tiene operaciones de acabado pendientes.")
    finishing_done_date = fields.Date(
        string='Fecha Término Acabado',
        compute='_compute_finishing_metrics', store=True,
        help="Día de término del acabado: fecha fin de la última operación de "
             "acabado, cuando ya no quedan operaciones de acabado pendientes.")
    is_in_finishing = fields.Boolean(
        string='En Acabado',
        compute='_compute_finishing_metrics', store=True,
        help="El ÁREA de la fase lista de la partida es ACABADO (campo `area`) y la "
             "ruta aún no terminó. Solo estas partidas cuentan como 'en acabado'; las "
             "que están en tintorería con acabado planificado más adelante (area != "
             "ACABADO) NO, y las que ya cerraron su última fase tampoco.")
    is_in_quality = fields.Boolean(
        string='En Control de Calidad',
        compute='_compute_finishing_metrics', store=True,
        help="El ÁREA de la fase lista de la partida es CONTROL DE CALIDAD (campo `area`) "
             "y la ruta aún no terminó (su última fase no está cerrada).")

    # ------------------------------------------------------------------
    # Reporte "Kilos x Pesar": partidas cuya ÚLTIMA fase de CONTROL DE
    # CALIDAD ya cerró (fecha inicio y fin) y que tienen kilos pesados en
    # SITPRO tinto_acab pero 0 kilos ingresados en alm_acab_ing (ambas
    # tablas SQL Server, base SITPRO, llave voucher = batch).
    # Los kilos NO son compute: los refresca _refresh_kilos_pesar() (cron
    # de sync y accion manual) porque vienen de SQL externo.
    # ------------------------------------------------------------------
    quality_last_start = fields.Datetime(
        string='Inicio Últ. C. Calidad',
        compute='_compute_finishing_metrics', store=True,
        help="Fecha de inicio (barFasDTI) de la ÚLTIMA fase de CONTROL DE "
             "CALIDAD de la ruta (mayor barOrdLin con operation_type=quality).")
    quality_last_end = fields.Datetime(
        string='Fin Últ. C. Calidad',
        compute='_compute_finishing_metrics', store=True,
        help="Fecha de fin (barFasDTF) de la ÚLTIMA fase de CONTROL DE "
             "CALIDAD de la ruta.")
    acab_weighed_kilos = fields.Float(
        string='Kilos Pesados (Acabado)', readonly=True,
        help="SUM(kneto) en SITPRO tinto_acab para voucher = batch. "
             "Refrescado por el sync o la accion 'Actualizar Kilos x Pesar'.")
    alm_ing_kilos = fields.Float(
        string='Kilos Ingreso Almacén', readonly=True,
        help="SUM(kneto) en SITPRO alm_acab_ing para voucher = batch. "
             "Refrescado por el sync o la accion 'Actualizar Kilos x Pesar'.")
    is_pending_weigh = fields.Boolean(
        string='Kilos x Pesar',
        compute='_compute_is_pending_weigh', store=True,
        help="Última fase de C. Calidad cerrada (inicio y fin), con kilos "
             "pesados en tinto_acab y 0 kilos en alm_acab_ing.")

    @api.depends('quality_last_start', 'quality_last_end',
                 'acab_weighed_kilos', 'alm_ing_kilos')
    def _compute_is_pending_weigh(self):
        for rec in self:
            rec.is_pending_weigh = bool(
                rec.quality_last_start and rec.quality_last_end
                and rec.acab_weighed_kilos > 0.0
                and not rec.alm_ing_kilos
            )

    @api.depends('area',
                 'proceso_ids.barFasDTI', 'proceso_ids.barFasDTF', 'proceso_ids.barOrdLin',
                 'proceso_ids.fas_code', 'proceso_ids.fasCod')
    def _compute_finishing_metrics(self):
        Op = self.env['mrp.routing.workcenter.operation'].sudo()
        type_by_code, type_by_name = {}, {}
        for op in Op.search([('operation_type', 'in', ('finishing', 'quality'))]):
            if op.fas_code:
                type_by_code[op.fas_code.strip().upper()] = op.operation_type
            if op.name:
                type_by_name.setdefault((op.name or '').strip().upper(), op.operation_type)

        def op_type(proc):
            code = (proc.fas_code or '').strip().upper()
            if code and code in type_by_code:
                return type_by_code[code]
            return type_by_name.get((proc.fasCod or '').strip().upper())

        for rec in self:
            procs = rec.proceso_ids.sorted(key=lambda p: p.barOrdLin or 0)
            finishing = [p for p in procs if op_type(p) == 'finishing']
            # Última fase de CONTROL DE CALIDAD de la ruta (mayor barOrdLin):
            # sus fechas alimentan el reporte "Kilos x Pesar".
            quality = [p for p in procs if op_type(p) == 'quality']
            last_quality = quality[-1] if quality else None
            rec.quality_last_start = last_quality.barFasDTI if last_quality else False
            rec.quality_last_end = last_quality.barFasDTF if last_quality else False
            # El conteo de operaciones de acabado pendientes arranca DESDE la
            # última fase TERMINADA (mayor barOrdLin con fecha fin). Las
            # operaciones de acabado anteriores a ese punto que quedaron sin
            # cerrar ya fueron superadas por la ruta — p. ej. tras un reproceso
            # la tela retrocede a tintorería y vuelve a avanzar, dejando atrás
            # fases de acabado planificadas que nunca se ejecutaron — así que NO
            # cuentan. Solo cuentan las de acabado pendientes posteriores a la
            # última fase terminada.
            finished_ords = [p.barOrdLin or 0 for p in procs if p.barFasDTF]
            last_done_ord = max(finished_ords) if finished_ords else -1
            pending_fin = [
                p for p in finishing
                if not p.barFasDTF and (p.barOrdLin or 0) > last_done_ord
            ]
            # La ruta ya terminó si su ÚLTIMA fase (mayor barOrdLin) tiene fecha
            # de inicio Y fin. TEXPLUS permite cerrar fases fuera de orden, así
            # que una partida puede tener fases de acabado anteriores sin cerrar
            # mientras su última fase ya está finalizada: en ese caso la ruta
            # terminó y NO está "en acabado".
            last_proc = procs[-1] if procs else None
            route_done = bool(last_proc and last_proc.barFasDTI and last_proc.barFasDTF)
            # Pertenencia según el ÁREA de la fase lista (campo `area`, derivado
            # del proceso siguiente), no de la primera fase pendiente: solo
            # ACABADO cuenta como acabado. Las partidas en tintorería con acabado
            # planificado más adelante tienen area != 'ACABADO' y NO aparecen.
            rec.is_in_finishing = (rec.area == 'ACABADO') and not route_done
            rec.is_in_quality = (rec.area == 'CONTROL DE CALIDAD') and not route_done
            rec.finishing_ops_pending = len(pending_fin)
            # Solo agrupa por "Operaciones N" si la partida está ACTUALMENTE en
            # acabado (área ACABADO y ruta no terminada).
            rec.finishing_ops_group = (
                'Operaciones %d' % len(pending_fin)
                if rec.is_in_finishing and pending_fin else False
            )
            done_date = False
            if finishing and not pending_fin:
                ends = [p.barFasDTF for p in finishing if p.barFasDTF]
                if ends:
                    # barFasDTF está en UTC: la fecha de término del acabado es
                    # el DÍA LOCAL (Perú) en que se cerró la última operación de
                    # acabado. Tomar .date() sobre el UTC adelantaba un día las
                    # fases cerradas de noche (p. ej. 22-jun 20:24 Lima =
                    # 23-jun 01:24 UTC).
                    done_date = pytz.utc.localize(max(ends)).astimezone(_PE_TZ).date()
            rec.finishing_done_date = done_date

    @api.model_create_multi
    def create(self, vals_list):
        # Default wish_date desde el pedido padre cuando no se especifica.
        pedido_cache = {}
        for vals in vals_list:
            if vals.get('wish_date'):
                continue
            pedido_id = vals.get('pedido_id')
            if not pedido_id:
                continue
            wd = pedido_cache.get(pedido_id)
            if wd is None:
                wd = self.env['control.pedido'].browse(pedido_id).wish_date or False
                pedido_cache[pedido_id] = wd
            if wd:
                vals['wish_date'] = wd
        return super().create(vals_list)

    def _auto_init(self):
        # Backfill NULL state to 'active' on module upgrades — idempotent
        # because the WHERE clause skips rows that already have a value.
        res = super()._auto_init()
        self.env.cr.execute(
            "UPDATE control_pedido_line SET state = 'active' WHERE state IS NULL"
        )
        return res

    def action_set_completed(self):
        self.write({'state': 'completed'})

    def action_set_active(self):
        self.write({'state': 'active'})

    # ------------------------------------------------------------------
    # Kilos x Pesar: refresh desde SITPRO SQL (tinto_acab / alm_acab_ing)
    # ------------------------------------------------------------------
    @api.model
    def refresh_kilos_pesar(self):
        """Refresca los kilos de las partidas candidatas al reporte:
        las activas con la última fase de C. Calidad cerrada, más las que
        hoy están marcadas (para des-marcarlas cuando almacén ya ingresó).
        Llamado desde el sync horario (_sync_extra_data) y utilizable a mano.
        """
        lines = self.search([
            '|',
            ('is_pending_weigh', '=', True),
            '&', ('state', '=', 'active'), ('quality_last_end', '!=', False),
        ])
        lines._refresh_kilos_pesar()
        return len(lines)

    def action_refresh_kilos_pesar(self):
        """Accion de servidor: refresca la selección; sin selección refresca
        todas las candidatas."""
        if self:
            self._refresh_kilos_pesar()
        else:
            self.refresh_kilos_pesar()

    def _refresh_kilos_pesar(self):
        """Escribe acab_weighed_kilos / alm_ing_kilos consultando SITPRO SQL
        por lotes (voucher = batch). Best-effort: si SQL no responde, deja los
        valores como están y registra el problema (el flag is_pending_weigh
        se recalcula solo al escribirse los kilos).

        Nota: voucher es varchar y SQL Server ignora espacios finales en la
        comparación, así que `voucher IN (...)` matchea aunque la columna
        venga con padding; el RTRIM solo hace falta en el SELECT.
        """
        lines = self.filtered(lambda l: (l.batch or '').strip())
        if not lines:
            return
        batches = sorted({l.batch.strip() for l in lines})
        try:
            conn = self.env['control.pedido']._get_sitpro_connection()
        except Exception:
            _logger.warning(
                "kilos x pesar: SITPRO SQL inalcanzable, kilos sin refrescar",
                exc_info=True)
            return
        acab, alm = {}, {}
        try:
            cursor = conn.cursor()
            chunk = 900
            for i in range(0, len(batches), chunk):
                part = batches[i:i + chunk]
                placeholders = ",".join(["?"] * len(part))
                cursor.execute(
                    f"SELECT LTRIM(RTRIM(voucher)), SUM(kneto) "
                    f"FROM tinto_acab WITH (NOLOCK) "
                    f"WHERE voucher IN ({placeholders}) "
                    f"GROUP BY LTRIM(RTRIM(voucher))",
                    *part,
                )
                for voucher, kilos in cursor.fetchall():
                    acab[voucher] = _safe_float(kilos)
                cursor.execute(
                    f"SELECT LTRIM(RTRIM(voucher)), SUM(kneto) "
                    f"FROM alm_acab_ing WITH (NOLOCK) "
                    f"WHERE voucher IN ({placeholders}) "
                    f"GROUP BY LTRIM(RTRIM(voucher))",
                    *part,
                )
                for voucher, kilos in cursor.fetchall():
                    alm[voucher] = _safe_float(kilos)
        except Exception:
            _logger.warning(
                "kilos x pesar: fallo la consulta a SITPRO, kilos sin refrescar",
                exc_info=True)
            return
        finally:
            conn.close()
        for line in lines:
            batch = line.batch.strip()
            vals = {}
            weighed = acab.get(batch, 0.0)
            ingressed = alm.get(batch, 0.0)
            if abs(line.acab_weighed_kilos - weighed) > 0.005:
                vals['acab_weighed_kilos'] = weighed
            if abs(line.alm_ing_kilos - ingressed) > 0.005:
                vals['alm_ing_kilos'] = ingressed
            if vals:
                line.write(vals)

    @api.depends('proceso_ids.barFasDTF', 'proceso_ids.barOrdLin', 'proceso_ids.fasCod')
    def _compute_next_process(self):
        for rec in self:
            pending = rec.proceso_ids.filtered(lambda p: not p.barFasDTF).sorted(
                key=lambda p: p.barOrdLin or 0
            )
            rec.next_process = pending[0].fasCod if pending else False

    @api.depends('next_process')
    def _compute_parent_operation_id(self):
        # next_process guarda el NOMBRE de la fase (FasDsc), p.ej. "CONTROL DE
        # CALIDAD", no el código. Por eso se machea contra operation.name (NO
        # fas_code) y se toma su fase padre. Batched.
        Op = self.env['mrp.routing.workcenter.operation']
        names = {(r.next_process or '').strip().upper() for r in self if r.next_process}
        names.discard('')
        parent_by_name = {}
        if names:
            for op in Op.sudo().search([]):
                key = (op.name or '').strip().upper()
                if key not in names:
                    continue
                parent = op.parent_operation_id.id or False
                # Si varias operaciones comparten nombre, prioriza una con padre.
                if key not in parent_by_name or (not parent_by_name[key] and parent):
                    parent_by_name[key] = parent
        for rec in self:
            key = (rec.next_process or '').strip().upper()
            rec.parent_operation_id = parent_by_name.get(key, False)

    @api.depends('area', 'proceso_ids.barFasDTI', 'proceso_ids.barFasDTF', 'proceso_ids.fas_code', 'report_date')
    def _compute_area_num_days(self):
        # The current area is derived (in SQL) from estatus_reproceso(fase=FasCod).
        # To know how long this line has been in `area`, we resolve the area of
        # every earlier process via the same SQL Server table, then walk
        # backwards through proceso_ids until we hit a process from a different
        # area. That boundary process tells us when the line entered its
        # current area: `change_date` = its date, `area_num_days` = days since
        # the first process of the current-area run.
        #
        # Special case: when CONTROL DE CALIDAD is the last phase of the
        # route AND the line has a ctrl_info `report_date`, we count days
        # from that report date instead — it's the moment the partida was
        # officially reported in QC and is more meaningful for follow-up.
        for rec in self:
            rec.area_num_days = 0
            rec.change_date = False

        records_with_data = self.filtered(lambda r: r.area and r.proceso_ids)
        if not records_with_data:
            return

        fas_codes = {
            p.fas_code
            for r in records_with_data
            for p in r.proceso_ids
            if p.fas_code
        }
        # Resolver el area de cada proceso con el MISMO criterio que `rec.area`:
        # primero el workcenter de Odoo (mas granular, ej: REPPRETA -> 'PRE
        # ACABADO'), y solo como respaldo el area legacy de estatus_reproceso
        # (donde REPPRETA -> 'ACABADO'). Si se usara solo estatus_reproceso, el
        # walk-back no detectaria el cambio de area en procesos como REPPRETA y
        # tomaria una fecha de un proceso anterior (ej: CONTROL DE CALIDAD).
        area_by_wc = self._fetch_areas_by_workcenter(fas_codes)
        area_by_fas = self._fetch_areas_by_fas_code(fas_codes)
        if not area_by_wc and not area_by_fas:
            return

        def _resolve_area(fas_code):
            if not fas_code:
                return False
            key = fas_code.strip().upper()
            return area_by_wc.get(key) or area_by_fas.get(fas_code)

        now = fields.Datetime.now()
        for rec in records_with_data:
            procs = rec.proceso_ids.sorted(key=lambda p: p.barOrdLin or 0)

            # Walk-back default: empezando por el proceso terminado mas
            # reciente, retroceder mientras estemos en la misma area. El
            # primer proceso de un area distinta marca cuando la linea
            # entro a su area actual.
            current_area = rec.area
            earliest_start = False
            walk_change_date = False
            for proc in reversed(procs):
                if not proc.barFasDTF:
                    continue
                proc_area = _resolve_area(proc.fas_code)
                if proc_area and proc_area != current_area:
                    walk_change_date = proc.barFasDTF or proc.barFasDTI
                    break
                if proc.barFasDTI:
                    earliest_start = proc.barFasDTI

            # report_date solo cuenta si la ULTIMA fase terminada de la
            # partida es CONTROL DE CALIDAD. Si despues de QC hubo otras
            # fases finalizadas (reprocesos, retornos a tintoreria/acabado,
            # etc.) el informe es viejo y el walk-back captura mejor el
            # estado actual.
            finished_procs = [p for p in procs if p.barFasDTF]
            last_finished = finished_procs[-1] if finished_procs else None
            calidad_is_last_finished = bool(
                last_finished
                and _resolve_area(last_finished.fas_code) == 'CONTROL DE CALIDAD'
            )
            report_dt = rec.report_date if (calidad_is_last_finished and rec.report_date) else False

            # change_date = el evento MAS RECIENTE entre:
            #   - el ultimo cambio de area (walk-back), y
            #   - la fecha del informe de QC.
            # Asi, si despues del QC la partida volvio a otra area y luego
            # a la actual, ese ultimo cambio gana sobre el informe viejo.
            candidates = [d for d in (walk_change_date, report_dt) if d]
            if candidates:
                rec.change_date = max(candidates)
                rec.area_num_days = self._count_days_excluding_sundays(rec.change_date, now)
            elif earliest_start:
                # No hubo cambio de area: contamos desde la primera fase
                # iniciada de la partida.
                rec.area_num_days = self._count_days_excluding_sundays(earliest_start, now)

    @api.model
    def _count_days_excluding_sundays(self, start_dt, end_dt):
        """Cuenta dias calendario entre `start_dt` y `end_dt` saltando domingos.
        Mismo criterio que `control.pedido._compute_num_days`."""
        if not start_dt or not end_dt:
            return 0
        start_d = start_dt.date() if hasattr(start_dt, 'date') else start_dt
        end_d = end_dt.date() if hasattr(end_dt, 'date') else end_dt
        if end_d < start_d:
            return 0
        days = 0
        current = start_d
        # weekday(): Monday=0 ... Sunday=6
        while current < end_d:
            if current.weekday() != 6:
                days += 1
            current += datetime.timedelta(days=1)
        return days

    @api.model
    def _fetch_areas_by_workcenter(self, fas_codes):
        """Return {FAS_CODE_UPPER: workcenter.name} for the given fas_codes.

        Usa el mismo mapeo de Odoo (`mrp.routing.workcenter.operation` ->
        `workcenter_id.name`) con el que `_vals_from_det_row` calcula el `area`
        de la partida. Es mas granular que `estatus_reproceso` (ej: REPPRETA
        cae en 'PRE ACABADO' aqui, pero en 'ACABADO' en TEXPLUS), asi que el
        walk-back de `_compute_area_num_days` debe usar este primero para que
        el area de cada proceso sea consistente con el area actual de la linea.
        """
        codes = {(fc or '').strip().upper() for fc in fas_codes if fc}
        codes.discard('')
        if not codes:
            return {}
        out = {}
        ops = self.env['mrp.routing.workcenter.operation'].sudo().search([
            ('fas_code', 'in', list(codes)),
        ])
        for op in ops:
            if op.workcenter_id and op.fas_code:
                out[op.fas_code.strip().upper()] = _canonical_area(op.workcenter_id.name)
        return out

    @api.model
    def _fetch_areas_by_fas_code(self, fas_codes):
        """Return {fas_code: area} for the given fas_codes, querying SQL Server.

        The mapping lives in the `estatus_reproceso` table (column `fase`
        joins BARFAS.FasCod, column `area` is the human-readable area).
        Returns an empty dict if anything goes wrong — callers must treat
        missing entries as "unknown area" and degrade gracefully.
        """
        fas_codes = [fc for fc in fas_codes if fc]
        if not fas_codes:
            return {}
        pedido = self.env['control.pedido']
        try:
            conn = pedido._get_sql_connection()
        except Exception:
            _logger.warning("control.pedido.line: SQL Server unreachable, area_num_days=0", exc_info=True)
            return {}
        out = {}
        try:
            cursor = conn.cursor()
            chunk = 900
            for i in range(0, len(fas_codes), chunk):
                batch = fas_codes[i:i + chunk]
                placeholders = ",".join(["?"] * len(batch))
                cursor.execute(
                    f"SELECT fase, area FROM estatus_reproceso WHERE fase IN ({placeholders})",
                    *batch,
                )
                for fase, area in cursor.fetchall():
                    out[_safe_str(fase)] = _canonical_area(_safe_str(area))
        except Exception:
            _logger.warning("control.pedido.line: failed to fetch estatus_reproceso", exc_info=True)
            return {}
        finally:
            conn.close()
        return out

    @api.model
    def _vals_from_det_row(self, dr):
        user_tz = pytz.timezone(self.env.user.tz or 'UTC')
        start = _safe_date(dr.get("FechaInicio"), user_tz)
        end = _safe_date(dr.get("FechaFinal"), user_tz)

        if start and start.year <= 1753:
            start = False
        if end and end.year <= 1753:
            end = False

        # Producto y lab.dev: usa mapas precargados del contexto si están
        # disponibles (evita N+1 en el sync masivo); si no, cae al search.
        codpro = (_safe_str(dr["BarSer"]) or '')[1:]
        colorcode = _safe_str(dr["ColorCode"]) or ''
        product_map = self.env.context.get('_product_by_code')
        if product_map is not None:
            product_id = product_map.get(codpro, False)
        else:
            product_id = self.env['product.template'].search([('default_code', '=', codpro)], limit=1).id or False
        lab_map = self.env.context.get('_lab_by_color')
        if lab_map is not None:
            lab_dev_id = lab_map.get(colorcode, False)
        else:
            lab_dev_id = self.env['lab.dev.line'].search([('color_code', '=', colorcode)], limit=1).id or False

        process = _safe_str(dr["Proceso_Ultimo"]) or 'SIN AVANCE'
        area = _safe_str(dr["Area"]) or 'VOUCHER'
        next_process = _safe_str(dr.get("Proceso_Siguiente"))
        # Override de area: si el caller paso un cache de fas_code -> workcenter.name
        # de Odoo, usamos el workcenter de la operacion del SIGUIENTE proceso.
        # Esto es mas granular que `estatus_reproceso` (ej: REPPRETA mapea a
        # 'ACABADO' en TEXPLUS pero a 'PRE ACABADO' en el workcenter de Odoo).
        # Fallback al area de TEXPLUS si no hay match.
        area_cache = self.env.context.get('_area_by_fas')
        if area_cache and next_process:
            wc_name = area_cache.get(next_process.strip().upper())
            if wc_name:
                area = wc_name
        # TERMINADO solo si CALIDAD es la ULTIMA fase de la ruta (no hay
        # proceso siguiente planificado, ni siquiera reprocesos), y tiene
        # fecha de inicio y fin cerradas.
        if (process.strip().upper() == 'CONTROL DE CALIDAD'
                and start and end
                and not next_process):
            area = 'TERMINADO'

        area = _canonical_area(area)

        return {
            "route": _safe_str(dr["HojaDeRuta"]),
            "barcodreo": _safe_str(dr["BarCodReo"]) or '',
            "description": _safe_str(dr["BarSerDsc"]),
            "codpro": codpro or '',
            "batch": _safe_str(dr["Partida"]) or '',
            "kilograms": _safe_float(dr["PesoTotal"]),
            "rollos": _safe_float(dr["Rollos"]),
            "process": process,
            "area": area,
            "start_date": start,
            "end_date": end,
            "colorcode": _safe_str(dr["ColorCode"]),
            "colorname": _safe_str(dr["ColorName"]),
            "product_id": product_id,
            "lab_dev_line_id": lab_dev_id,
        }

    def action_open_start_wizard(self):
        self.ensure_one()
        # Buscar el primer proceso pendiente
        pending = self.proceso_ids.filtered(lambda p: not p.barFasDTI).sorted('barOrdLin')[:1]
        if not pending:
            from odoo.exceptions import UserError
            raise UserError("No hay procesos pendientes para iniciar.")
            
        return {
            'name': 'Confirmar Inicio de Proceso',
            'type': 'ir.actions.act_window',
            'res_model': 'btn.inicio.fase.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_line_id': pending.id,
            }
        }

    def action_start_process(self):
        for rec in self:
            pending = rec.proceso_ids.filtered(lambda p: not p.barFasDTI).sorted('barOrdLin')[:1]
            if pending:
                # El método action_start requiere argumentos que no tenemos aquí directamente
                # Se recomienda usar el wizard o implementar una acción por defecto
                pass
            else:
                rec.start_date = fields.Datetime.now()

    def action_end_process(self):
        for rec in self:
            active = rec.proceso_ids.filtered(lambda p: p.barFasDTI and not p.barFasDTF).sorted('barOrdLin', reverse=True)[:1]
            if active:
                active.action_finish()
            else:
                rec.end_date = fields.Datetime.now()


class MrpRoutingWorkcenterOperation(models.Model):
    """Extensión de la operación: cuando cambia la jerarquía de fases
    (parent_operation_id) o el name de una operación, recalcula el
    `parent_operation_id` (computado) de las partidas cuyo `next_process` apunta
    a esa operación. Sin esto, las partidas ya calculadas no reflejarían un
    cambio de padre hecho después. (Va en este archivo y no en uno propio para
    evitar problemas de import.)"""
    _inherit = 'mrp.routing.workcenter.operation'

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._recompute_partidas_parent_operation()
        return records

    def write(self, vals):
        res = super().write(vals)
        if 'parent_operation_id' in vals or 'name' in vals:
            self._recompute_partidas_parent_operation()
        return res

    def _recompute_partidas_parent_operation(self):
        # Las partidas machean por NOMBRE de operación (next_process = FasDsc),
        # no por fas_code.
        names = [n for n in self.mapped('name') if n]
        if not names:
            return
        lines = self.env['control.pedido.line'].sudo().search(
            [('next_process', 'in', names)])
        # Marcar next_process como modificado fuerza el recálculo de
        # parent_operation_id (que depende de él).
        if lines:
            lines.modified(['next_process'])
