# -*- coding: utf-8 -*-
from dbf import Char
import datetime
import logging
import pyodbc
import pytz
import time
pyodbc.setDecimalSeparator(".")
from odoo import models, fields, api, _
from odoo.exceptions import UserError
from odoo.addons.idtx_mrp.models.mrp_routing_workcenter_operation import (
    _ReadOnlyTexplusConnection,
    _texplus_writes_enabled,
)
import dbf

from .utils import _safe_str, _safe_float, _safe_date, _safe_bool

_logger = logging.getLogger(__name__)

# ---------- Helpers DBF ----------
def _read_dbf(filename, limit=None, nums=None):
    t = dbf.Table(filename, codepage="cp1252")
    t.open(mode=dbf.READ_ONLY)
    try:
        rows = []
        i = 0
        for rec in t:
            if _filter_rec(filename, rec, nums):
                continue
            if bool(dbf.is_deleted(rec)):
                continue
            if limit and i >= limit:
                break
            rows.append({fn: rec[fn] for fn in t.field_names})
            i += 1
        return rows
    finally:
        t.close()

def _iter_dbf(dbf_path):
    t = dbf.Table(dbf_path, codepage="cp1252")
    t.open(mode=dbf.READ_ONLY)
    try:
        for rec in t:
            if dbf.is_deleted(rec):
                continue
            yield rec
    finally:
        t.close()

def _sum_kneto_by_pedido(dbf_path, nums_set):
    t = dbf.Table(dbf_path, codepage="cp1252")
    t.open(mode=dbf.READ_ONLY)
    try:
        out = {}
        for rec in t:
            if dbf.is_deleted(rec):
                continue
            pnum = _safe_str(rec["NUMORDPED"])
            if not pnum or pnum not in nums_set:
                continue
            out[pnum] = out.get(pnum, 0.0) + _safe_float(rec["KNETO"])
        return out
    finally:
        t.close()

def _filter_rec(filename, rec, nums):
    if filename == '/mnt/fox/sit06/dbf/vta_cab_pedido.dbf':
        if rec['FECOC'] is None or \
            not _safe_date(rec['FECOC']) or \
            rec['FECOC'] < datetime.date(2025,6,30) or \
            not _safe_bool(rec['activo']) or \
            _safe_str(rec['tipoventa'][:10]) != 'VENTA DE T':
            return True
    else:
        pnum = _safe_str(rec["NUMORDPED"])
        if not pnum or pnum not in nums:
            return True
    return False

def _settle_order_dbf(filename, order, is_active):
    table = dbf.Table(filename, codepage='cp1252')
    table.open(mode=dbf.READ_WRITE)
    try:
        for rec in table:
            if _safe_str(rec['NUMORDPED']) == order:
                with rec:
                    rec['ACTIVO'] = is_active
                return True
        return False
    finally:
        table.close()


def _barcodreo_rank(value):
    """Return a numeric rank for BarCodReo values so we can keep the latest one."""
    return _safe_float(value) or 0.0

FIRST_AREA = {'PRE TINTORERIA', 'TEJEDURIA'}
SECOND_AREA = {'TINTORERIA', 'PRE ESTAMPADO'}
THIRD_AREA = {'ESTAMPADO', 'PRE ACABADO'}
FOURTH_AREA = {'ACABADO', 'CONTROL DE CALIDAD'}

# ---------- Models ----------
class ControlPedido(models.Model):
    _name = "control.pedido"
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = "Control de Pedido"
    _order = "fecoc desc, numordped desc, num_days desc, state desc"
    _rec_name = 'numordped'

    fecha = fields.Date(string="Order Date")
    fecoc = fields.Date(string="Customer Order Date")
    fecgvtas = fields.Date(string="Fecha Gerencia Ventas")
    feccc = fields.Date(string="Fecha Aprobación")
    numordped = fields.Char(string="Order Number", required=True, index=True)
    customer = fields.Char('Customer')
    # salesman = fields.Char('Salesman')
    # cdgven = fields.Char('Salesman Code')
    user_id = fields.Many2one('res.users', string='Salesman')
    tipoventa = fields.Char(string="Type of Sale")
    oc_cliente = fields.Char(string="O/C Cliente", help="Orden de compra del cliente (OCC en vta_cab_pedido).")
    observaciones = fields.Text(string="Observaciones", help="Observaciones del pedido (OBSERV en vta_cab_pedido).")
    total_weight = fields.Float('Total Weight')
    produced_weight = fields.Float('Produced Weight')
    wish_date = fields.Date('Fecha Deseada',
        help="Fecha objetivo para la entrega del pedido. Al modificarla se "
             "propaga a todas las partidas hijas (las modificaciones manuales "
             "previas en las lineas se sobrescriben).")
    line_ids = fields.One2many("control.pedido.line", "pedido_id", string="Detail")
    process = fields.Char('Process', compute='_compute_process', store=True)
    area = fields.Char('Area', compute='_compute_process', store=True)
    is_active = fields.Boolean('is_active?')
    # Desactivación SOLO para el reporte "Planning por OP". Es independiente de
    # is_active/state y NO toca el DBF de SITPRO: plan_active=False oculta la OP
    # del Planning (vía el dominio de la acción) sin afectar ningún otro
    # reporte/vista ni el estado del pedido.
    plan_active = fields.Boolean('Activo en Planning', default=True, index=True, copy=False)
    plan_days_oc_cc = fields.Integer(
        'Días OC→Aprobación', compute='_compute_plan_days_oc_cc', store=True,
        help="Días calendario desde fecoc (Fecha OC Cliente) hasta feccc "
             "(Fecha Aprobación).")
    num_days = fields.Integer('Number of Days', compute='_compute_num_days', store=True)
    # --- Planning por OP: fechas estimadas a partir de feccc (Fecha Aprobación) ---
    plan_has_thermo = fields.Boolean(
        'Tiene Termofijado', compute='_compute_plan_has_thermo', store=True,
        help="Verdadero si algún producto del pedido tiene una fase cuyo nombre "
             "contiene 'THERMO' en la ruta de su ficha técnica.")
    plan_weaving_start = fields.Date(
        'Inicio Tejido', compute='_compute_plan_dates', store=True,
        help="Fecha Aprobación (feccc) + 2 días hábiles (excl. domingos).")
    plan_weaving_end = fields.Date(
        'Fin Tejido', compute='_compute_plan_dates', store=True,
        help="Inicio de tejido + 7 días hábiles (excl. domingos).")
    plan_thermo_start = fields.Date(
        'Inicio Termofijado', compute='_compute_plan_dates', store=True,
        help="Inicio de tejido + 2 días hábiles (excl. domingos). Solo si el "
             "pedido tiene termofijado.")
    plan_thermo_end = fields.Date(
        'Fin Termofijado', compute='_compute_plan_dates', store=True,
        help="Inicio de termofijado + 7 días hábiles (excl. domingos). Solo si "
             "el pedido tiene termofijado.")
    plan_dyeing_start = fields.Date(
        'Inicio Teñido', compute='_compute_plan_dates', store=True,
        help="Fin de tejido.")
    plan_dyeing_end = fields.Date(
        'Fin Teñido', compute='_compute_plan_dates', store=True,
        help="Inicio de teñido + 14 días hábiles (excl. domingos).")
    plan_finishing_start = fields.Date(
        'Inicio Acabado', compute='_compute_plan_dates', store=True,
        help="Fin de teñido.")
    plan_finishing_end = fields.Date(
        'Fin Acabado', compute='_compute_plan_dates', store=True,
        help="Inicio de acabado + 14 días hábiles (excl. domingos).")
    plan_kilos_to_dye = fields.Float(
        'Kilos de OP', compute='_compute_plan_kilos_to_dye', store=True, digits=(12, 2),
        help="Total de kilos pedidos de la OP (TOTKIL / total_weight): suma de "
             "los kilos de todos los productos del pedido. Es el denominador del "
             "% de avance de teñido y de acabado.")
    plan_kilos_dyed = fields.Float(
        'Kilos Teñidos', compute='_compute_plan_kilos_dyed', store=True, digits=(12, 2),
        help="Suma de kilos de las partidas de la OP cuya fase de teñido ya está "
             "terminada (con fecha de inicio y fin). Fase de teñido = nombre con "
             "'TEÑIDO', excluyendo RETEÑIDO y SUAVIZADO EN MAQ TEÑIDO.")
    plan_dye_progress = fields.Float(
        '% Avance Teñido', compute='_compute_plan_dye_progress', store=True, digits=(5, 2),
        help="Kilos teñidos / kilos de OP × 100, topado a 100%.")
    plan_weave_progress = fields.Float(
        '% Avance Tejido', compute='_compute_plan_weave_progress', store=True, digits=(5, 2),
        help="Kilos tejidos (produced_weight = suma de KNETO de tej_produccion.dbf "
             "por OP, vía NUMORDPED/OT) / kilos de OP × 100, topado a 100%.")
    plan_kilos_thermo = fields.Float(
        'Kilos Termofijados', compute='_compute_plan_kilos_thermo', store=True, digits=(12, 2),
        help="Suma de kilos de las partidas de la OP cuya fase de termofijado ya "
             "está terminada (con fecha de inicio y fin). Fase = nombre con "
             "'THERMOFIJADO' (excluye 'PREPARADO PARA TERMOFIJAR' y reprocesos).")
    plan_thermo_progress = fields.Float(
        '% Avance Termofijado', compute='_compute_plan_thermo_progress', store=True, digits=(5, 2),
        help="Kilos termofijados / kilos de OP × 100, topado a 100%.")
    plan_kilos_finished = fields.Float(
        'Kilos Acabados', compute='_compute_plan_kilos_finished', store=True, digits=(12, 2),
        help="Suma de kilos de las partidas de la OP cuyo acabado ya está "
             "terminado (todas sus operaciones de acabado cerradas; campo "
             "finishing_done_date de la partida).")
    plan_finish_progress = fields.Float(
        '% Avance Acabado', compute='_compute_plan_finish_progress', store=True, digits=(5, 2),
        help="Kilos acabados / kilos de OP × 100, topado a 100%.")
    plan_schedule_alert = fields.Selection(
        [('danger', 'Atrasado'), ('warning', 'Por vencer')],
        string='Alerta Cronograma', compute='_compute_plan_schedule_alert',
        help="Comparando cada proceso (tejido, termofijado si hay, teñido, "
             "acabado) con su fecha final: si hoy ya pasó la fecha final del "
             "proceso y su avance es ≤80% → Atrasado (rojo); si el avance está "
             "entre 80% y 100% → Por vencer (naranja). NO almacenado: se "
             "recalcula con la fecha de hoy cada vez que se abre la vista.")
    state = fields.Selection([
        ('on', 'On Time'),
        ('de', 'Delayed'),
        ('do', 'Done'),
        ('se', 'Settled'),
    ], string='State', compute='_compute_state', default='on', store=True, tracking=True)

    _product_code_unique = models.Constraint('unique(numordped)', "Ya existe un pedido con ese Número de Orden!")

    @api.depends('feccc', 'fecgvtas', 'fecoc')
    def _compute_num_days(self):
        # Base date fallback: feccc (aprobacion) -> fecgvtas (gerencia ventas)
        # -> fecoc (oc cliente). El conteo excluye domingos.
        today = fields.Date.context_today(self)
        for rec in self:
            base = rec.fecha or rec.fecoc or rec.feccc or rec.fecgvtas
            if not base:
                rec.num_days = 0
                continue
            days = 0
            current = base
            while current <= today:
                if current.weekday() != 6:
                    days += 1
                current += datetime.timedelta(days=1)
            rec.num_days = days

    @api.depends('line_ids.product_id')
    def _compute_plan_has_thermo(self):
        """Verdadero si algún producto del pedido tiene una operación cuyo
        nombre contiene 'THERMO' en la ruta de su ficha técnica. Se calcula en
        lote: una sola consulta para el conjunto de productos con termofijado."""
        thermo_ops = self.env['mrp.routing.workcenter.operation'].sudo().search(
            [('name', 'ilike', 'THERMO')])
        thermo_product_ids = set()
        if thermo_ops:
            route_lines = self.env['technical.route.line'].sudo().search(
                [('operation_id', 'in', thermo_ops.ids)])
            analyses = route_lines.mapped('technical_id.analysis_id')
            if analyses:
                products = self.env['product.template'].sudo().search(
                    [('analysis_id', 'in', analyses.ids)])
                thermo_product_ids = set(products.ids)
        for rec in self:
            rec.plan_has_thermo = bool(thermo_product_ids & set(rec.line_ids.product_id.ids))

    @api.depends('feccc', 'plan_has_thermo')
    def _compute_plan_dates(self):
        """Fechas estimadas de planning desde feccc (Fecha Aprobación),
        contando solo días hábiles (se EXCLUYEN los domingos): los offsets
        +2/+7/+14 saltan domingos y ninguna fecha resultante cae en domingo.
          - Tejido: inicio = feccc + 2; fin = inicio + 7.
          - Termofijado (solo si plan_has_thermo): inicio = inicio tejido + 2;
            fin = inicio + 7.
          - Teñido: inicio = fin de tejido; fin = inicio + 14.
          - Acabado: inicio = fin de teñido; fin = inicio + 14.
        """
        def add_days(start, n):
            # Avanza n días saltando domingos (weekday() == 6). El resultado
            # nunca cae en domingo (el último día contado es no-domingo).
            d = start
            added = 0
            while added < n:
                d += datetime.timedelta(days=1)
                if d.weekday() != 6:
                    added += 1
            return d
        for rec in self:
            base = rec.feccc
            if not base:
                rec.plan_weaving_start = rec.plan_weaving_end = False
                rec.plan_thermo_start = rec.plan_thermo_end = False
                rec.plan_dyeing_start = rec.plan_dyeing_end = False
                rec.plan_finishing_start = rec.plan_finishing_end = False
                continue
            weaving_start = add_days(base, 2)
            weaving_end = add_days(weaving_start, 7)
            rec.plan_weaving_start = weaving_start
            rec.plan_weaving_end = weaving_end
            if rec.plan_has_thermo:
                thermo_start = add_days(weaving_start, 2)
                rec.plan_thermo_start = thermo_start
                rec.plan_thermo_end = add_days(thermo_start, 7)
            else:
                rec.plan_thermo_start = rec.plan_thermo_end = False
            dyeing_start = weaving_end
            dyeing_end = add_days(dyeing_start, 14)
            rec.plan_dyeing_start = dyeing_start
            rec.plan_dyeing_end = dyeing_end
            rec.plan_finishing_start = dyeing_end
            rec.plan_finishing_end = add_days(dyeing_end, 14)

    @api.depends('total_weight')
    def _compute_plan_kilos_to_dye(self):
        """Kilos a teñir = total de kilos pedidos de la OP (TOTKIL =
        total_weight, la suma de los kilos de todos los productos del pedido).
        OJO: NO usar la suma de partidas (line_ids) — esas son la producción
        real (parcial o con reprocesos) y no el total pedido."""
        for rec in self:
            rec.plan_kilos_to_dye = rec.total_weight

    @staticmethod
    def _is_dyeing_phase_name(fas_name):
        """True si el nombre de fase corresponde a TEÑIDO real: contiene
        'TEÑIDO' pero NO 'RETEÑIDO' (re-teñido/reproceso) ni 'SUAVIZADO'
        (suavizado hecho en máquina de teñido, no es teñido)."""
        name = (fas_name or '').upper()
        return 'TEÑIDO' in name and 'RETEÑIDO' not in name and 'SUAVIZADO' not in name

    @api.depends('line_ids.kilograms', 'line_ids.proceso_ids.fasCod',
                 'line_ids.proceso_ids.barFasDTI', 'line_ids.proceso_ids.barFasDTF')
    def _compute_plan_kilos_dyed(self):
        """Suma de kilos de las partidas (líneas) cuya fase de teñido está
        terminada: alguna fase (proceso) de teñido real (ver
        `_is_dyeing_phase_name`) con fecha de inicio (barFasDTI) y de fin
        (barFasDTF)."""
        for rec in self:
            total = 0.0
            for line in rec.line_ids:
                if any(p.barFasDTI and p.barFasDTF
                       and self._is_dyeing_phase_name(p.fasCod)
                       for p in line.proceso_ids):
                    total += line.kilograms or 0.0
            rec.plan_kilos_dyed = total

    @api.depends('plan_kilos_dyed', 'plan_kilos_to_dye')
    def _compute_plan_dye_progress(self):
        """Porcentaje de avance de teñido = kilos teñidos / kilos de OP × 100,
        topado a 100% (puede haber reprocesos donde lo teñido supera lo pedido)."""
        for rec in self:
            if rec.plan_kilos_to_dye:
                rec.plan_dye_progress = min(
                    rec.plan_kilos_dyed / rec.plan_kilos_to_dye * 100.0, 100.0)
            else:
                rec.plan_dye_progress = 0.0

    @staticmethod
    def _is_thermo_phase_name(fas_name):
        """True si el nombre de fase corresponde a TERMOFIJADO real: contiene
        'THERMOFIJADO'. Excluye naturalmente 'PREPARADO PARA TERMOFIJAR'
        (preparación, sin H y termina en -AR) y reprocesos."""
        return 'THERMOFIJADO' in (fas_name or '').upper()

    @api.depends('line_ids.kilograms', 'line_ids.proceso_ids.fasCod',
                 'line_ids.proceso_ids.barFasDTI', 'line_ids.proceso_ids.barFasDTF')
    def _compute_plan_kilos_thermo(self):
        """Suma de kilos de las partidas cuya fase de termofijado está terminada:
        alguna fase (proceso) con 'THERMOFIJADO' en el nombre (fasCod) con fecha
        de inicio (barFasDTI) y de fin (barFasDTF). Mismo esquema que teñido."""
        for rec in self:
            total = 0.0
            for line in rec.line_ids:
                if any(p.barFasDTI and p.barFasDTF
                       and self._is_thermo_phase_name(p.fasCod)
                       for p in line.proceso_ids):
                    total += line.kilograms or 0.0
            rec.plan_kilos_thermo = total

    @api.depends('plan_kilos_thermo', 'plan_kilos_to_dye')
    def _compute_plan_thermo_progress(self):
        """Porcentaje de avance de termofijado = kilos termofijados / kilos de OP
        × 100, topado a 100%."""
        for rec in self:
            if rec.plan_kilos_to_dye:
                rec.plan_thermo_progress = min(
                    rec.plan_kilos_thermo / rec.plan_kilos_to_dye * 100.0, 100.0)
            else:
                rec.plan_thermo_progress = 0.0

    @api.depends('produced_weight', 'plan_kilos_to_dye')
    def _compute_plan_weave_progress(self):
        """Porcentaje de avance de tejido = kilos tejidos (produced_weight, de
        tej_produccion.dbf) / kilos de OP × 100, topado a 100% (se teje algo de
        más, así que el tejido puede superar lo pedido)."""
        for rec in self:
            if rec.plan_kilos_to_dye:
                rec.plan_weave_progress = min(
                    rec.produced_weight / rec.plan_kilos_to_dye * 100.0, 100.0)
            else:
                rec.plan_weave_progress = 0.0

    @api.depends('line_ids.kilograms', 'line_ids.finishing_done_date')
    def _compute_plan_kilos_finished(self):
        """Suma de kilos de las partidas cuyo acabado está terminado: la partida
        tiene finishing_done_date (todas sus operaciones de acabado cerradas)."""
        for rec in self:
            rec.plan_kilos_finished = sum(
                line.kilograms or 0.0
                for line in rec.line_ids
                if line.finishing_done_date
            )

    @api.depends('plan_kilos_finished', 'plan_kilos_to_dye')
    def _compute_plan_finish_progress(self):
        """Porcentaje de avance de acabado = kilos acabados / kilos de OP × 100,
        topado a 100%."""
        for rec in self:
            if rec.plan_kilos_to_dye:
                rec.plan_finish_progress = min(
                    rec.plan_kilos_finished / rec.plan_kilos_to_dye * 100.0, 100.0)
            else:
                rec.plan_finish_progress = 0.0

    @api.depends('plan_weaving_end', 'plan_weave_progress',
                 'plan_has_thermo', 'plan_thermo_end', 'plan_thermo_progress',
                 'plan_dyeing_end', 'plan_dye_progress',
                 'plan_finishing_end', 'plan_finish_progress')
    def _compute_plan_schedule_alert(self):
        """Alerta de cronograma. Solo cuenta el ÚLTIMO proceso CON AVANCE (>0%)
        en la cadena tejido → termofijado (si hay) → teñido → acabado: los
        procesos anteriores sin terminar no importan (su 0% suele ser un hueco de
        medición, p. ej. tejido/teñido en 0 pero acabado al 99%). Sobre ese
        proceso, comparando con SU fecha final:
          - hoy ya pasó la fecha y avance ≤ 80% → Atrasado (danger / rojo)
          - hoy ya pasó la fecha y 80% < avance < 100% → Por vencer (warning)
          - en otro caso → sin alerta.
        Si ningún proceso tiene avance, se evalúa el tejido (primer proceso).
        NO almacenado: depende de la fecha de hoy, se recalcula al leer."""
        today = fields.Date.context_today(self)
        for rec in self:
            chain = [(rec.plan_weaving_end, rec.plan_weave_progress)]
            if rec.plan_has_thermo:
                chain.append((rec.plan_thermo_end, rec.plan_thermo_progress))
            chain.append((rec.plan_dyeing_end, rec.plan_dye_progress))
            chain.append((rec.plan_finishing_end, rec.plan_finish_progress))
            # Último proceso con avance > 0; si ninguno, el primero (tejido).
            current = chain[0]
            for end_date, progress in chain:
                if progress > 0:
                    current = (end_date, progress)
            end_date, progress = current
            alert = False
            if end_date and today > end_date:
                if progress <= 80.0:
                    alert = 'danger'
                elif progress < 100.0:
                    alert = 'warning'
            rec.plan_schedule_alert = alert

    @api.depends('line_ids','num_days','is_active')
    def _compute_state(self):
        for rec in self:
            result = 'on'
            suma = sum(rec.line_ids.mapped('kilograms') or [0.0])
            if rec.num_days:
                if not len(rec.line_ids) and rec.num_days > 12:
                    result = 'de'
                elif len(rec.line_ids) and rec.num_days > 12 and any(l.area in FIRST_AREA for l in rec.line_ids) and suma < rec.total_weight:
                    result = 'de'
                elif rec.num_days > 12 and rec.num_days <= 20:
                    if any(l.area in SECOND_AREA for l in rec.line_ids) or rec.area == 'TEJEDURIA':
                        result = 'de'
                elif rec.num_days > 20 and rec.num_days <= 25:
                    if any(l.area in THIRD_AREA for l in rec.line_ids) or rec.area == 'TEJEDURIA':
                        result = 'de'
                elif rec.num_days > 25 and rec.num_days <= 30:
                    if any(l.area in FOURTH_AREA for l in rec.line_ids) or rec.area == 'TEJEDURIA':
                        result = 'de'
                elif rec.num_days > 30:
                    result = 'de'
                if sum(rec.line_ids.mapped('kilograms')) >= rec.total_weight and all(l.area in FOURTH_AREA and l.start_date and l.end_date for l in rec.line_ids):
                    result = 'do'
                if not rec.is_active:
                    result = 'se'
            rec.state = result

    @api.depends('line_ids', 'line_ids.area', 'line_ids.kilograms', 'total_weight')
    def _compute_process(self):
        for rec in self:
            suma = sum(rec.line_ids.mapped('kilograms') or [0.0])
            if not rec.line_ids or suma < rec.total_weight:
                rec.process = 'TEJIDO'
                rec.area = 'TEJEDURIA'
                continue
            first = rec.line_ids.filtered(lambda l: l.area in FIRST_AREA)
            second = rec.line_ids.filtered(lambda l: l.area in SECOND_AREA)
            third = rec.line_ids.filtered(lambda l: l.area in THIRD_AREA)
            fourth = rec.line_ids.filtered(lambda l: l.area in FOURTH_AREA)
            chosen = (first or second or third or fourth)[:1]
            if chosen:
                line = chosen[0]
                rec.process = line.process or 'FASE NO RECONOCIDA'
                rec.area = line.area or 'AREA NO CONOCIDA'
            else:
                rec.process = 'SIN AVANCE'
                rec.area = 'AREA NO CONOCIDA'

    _WISH_DATE_OFFSET_DAYS = 45

    @api.model_create_multi
    def create(self, vals_list):
        # Default wish_date = fecoc + 45 dias si no se especifico.
        for vals in vals_list:
            if not vals.get('wish_date') and vals.get('fecoc'):
                fecoc = vals['fecoc']
                if isinstance(fecoc, str):
                    fecoc = fields.Date.from_string(fecoc)
                if fecoc:
                    vals['wish_date'] = fecoc + datetime.timedelta(days=self._WISH_DATE_OFFSET_DAYS)
        return super().create(vals_list)

    def write(self, vals):
        # Si llega fecoc y no llega wish_date explicito, calculamos el
        # default (fecoc + 45) SOLO para los pedidos que aun no tienen
        # wish_date seteado (no pisamos ediciones manuales del usuario).
        auto_wish_by_id = {}
        if 'fecoc' in vals and 'wish_date' not in vals:
            fecoc = vals.get('fecoc')
            if isinstance(fecoc, str):
                fecoc = fields.Date.from_string(fecoc)
            if fecoc:
                default_wish = fecoc + datetime.timedelta(days=self._WISH_DATE_OFFSET_DAYS)
                for rec in self:
                    if not rec.wish_date:
                        auto_wish_by_id[rec.id] = default_wish

        # Si wish_date cambia explicitamente, propagar el nuevo valor a
        # todas las lineas. Las modificaciones manuales previas en partidas
        # se pierden — semantica del "default propagable" pedido -> partida.
        propagate_wish = 'wish_date' in vals
        res = super().write(vals)
        if propagate_wish:
            new_date = vals.get('wish_date') or False
            for rec in self:
                if rec.line_ids:
                    rec.line_ids.write({'wish_date': new_date})
        # Aplicar el default calculado a los registros que correspondan.
        for pid, wd in auto_wish_by_id.items():
            self.browse(pid).write({'wish_date': wd})
        return res

    def settle_order(self):
        res = _settle_order_dbf("/mnt/fox/sit06/dbf/vta_cab_pedido.dbf", self.numordped, not self.is_active)
        if res:
            new_active = not self.is_active
            self.is_active = new_active
            # Propagar al estado de las lineas:
            # - Liquidacion (is_active False -> state='se'): lineas a 'completed'.
            # - Reversion (is_active True): lineas vuelven a 'active' y
            #   forzamos recompute de los campos derivados (area_num_days,
            #   change_date) porque sus @api.depends no escuchan a `state`.
            line_state = 'active' if new_active else 'completed'
            self.line_ids.write({'state': line_state})
            if new_active and self.line_ids:
                self.line_ids._compute_area_num_days()
        return res

    def action_plan_deactivate(self):
        """Desactiva las OPs seleccionadas SOLO para el reporte 'Planning por
        OP' (plan_active=False). NO toca is_active/state ni el DBF de SITPRO,
        por lo que no afecta ningún otro reporte."""
        self.write({'plan_active': False})

    def action_plan_activate(self):
        """Reactiva las OPs seleccionadas en el reporte 'Planning por OP'
        (plan_active=True)."""
        self.write({'plan_active': True})

    @api.depends('fecoc', 'feccc')
    def _compute_plan_days_oc_cc(self):
        for rec in self:
            if rec.fecoc and rec.feccc:
                rec.plan_days_oc_cc = (rec.feccc - rec.fecoc).days
            else:
                rec.plan_days_oc_cc = 0

    def _get_sql_connection(self):
        try:
            conn = pyodbc.connect(
                "DSN=ENBTEX1_DSN;PORT=1433;UID=sistemas;PWD=idtE#21@IRdc95;TDS_Version=7.3;"
            )
        except Exception as e:
            raise UserError(f"No se pudo conectar a SQL Server: {e}")
        if not _texplus_writes_enabled():
            return _ReadOnlyTexplusConnection(conn)
        return conn

    def _get_sitpro_connection(self):
        try:
            conn = pyodbc.connect(
                "DSN=SITPRO_DSN;PORT=1433;UID=sistemas;PWD=idtE#21@IRdc95;TDS_Version=7.3;"
            )
            return conn
        except Exception as e:
            raise UserError(f"No se pudo conectar a SITPRO: {e}")
        
    @api.model
    def sync_from_dbf(self):
        _sync_t0 = time.perf_counter()
        cab_by_num = {}
        nums = []
        nums_seen = set()
        nums_to_settle = []
        # Lectura exhaustiva del DBF: TODOS los pedidos (activos e inactivos)
        # se procesan en cada sync para refrescar sus datos. Antes solo se
        # procesaban activos y los inactivos quedaban congelados, lo que
        # causaba que correcciones en SITPRO (fechas, customer, kilos, etc.)
        # no se reflejaran en Odoo.
        for rec in _iter_dbf("/mnt/fox/sit06/dbf/vta_cab_pedido.dbf"):
            fecha = rec["FECHA"]
            if not fecha or fecha < datetime.date(2025, 6, 30):
                continue
            num = _safe_str(rec["NUMORDPED"])
            if not num:
                continue
            is_active = _safe_bool(rec["ACTIVO"])
            if not is_active:
                nums_to_settle.append(num)
            if num not in nums_seen:
                nums_seen.add(num)
                nums.append(num)
            cab_by_num[num] = {
                "fecha": _safe_date(rec["FECHA"]),
                "fecoc": _safe_date(rec["FECOC"]),
                "fecgvtas": _safe_date(rec["FECGVTAS"]),
                "feccc": _safe_date(rec["FECCC"]),
                "customer": _safe_str(rec["RAZSOC"]),
                "user_id": self.env['res.users'].search([('vendor_code_sitpro', '=', _safe_str(rec["CDGVEN"]))], limit=1).id,
                "tipoventa": _safe_str(rec["TIPOVENTA"]),
                "oc_cliente": _safe_str(rec["OCC"]),
                "observaciones": _safe_str(rec["OBSERV"]),
                "total_weight": _safe_float(rec["TOTKIL"]),
                "is_active": is_active,
            }

        if not nums:
            return {"created": 0, "updated": 0}

        # is_active de pedidos inactivos ya viene en cab_by_num y se
        # aplica en pedido.write(vals) mas abajo, asi que no necesitamos
        # un bulk-write separado.
        nums_set = set(nums)
        produced_by_num = _sum_kneto_by_pedido("/mnt/fox/sit06/dbf/tej_produccion.dbf", nums_set)
        existing = self.browse()
        search_chunk = 2000
        for i in range(0, len(nums), search_chunk):
            existing |= self.search([("numordped", "in", nums[i:i + search_chunk])])
        existing_map = {p.numordped: p for p in existing}
        created = 0
        updated = 0
        pedidos = self.browse()
        for num in nums:
            base = cab_by_num[num]
            vals = {**base, 'numordped': num, 'produced_weight': produced_by_num.get(num, 0.0)}
            pedido = existing_map.get(num)
            if pedido:
                pedido.write(vals)
                updated += 1
            else:
                pedido = self.create(vals)
                created += 1
                existing_map[num] = pedido
            pedidos |= pedido
        # Indices de lineas existentes:
        # - by_full_key: (route, batch, codpro) -> match exacto preferente.
        # - by_route_batch: (route, batch) -> fallback cuando el codpro
        #   historico era distinto (campo vacio o con un prefijo diferente).
        #   Evita duplicar lineas zombies cuando la logica de codpro cambia.
        existing_lines_by_pedido = {}
        existing_by_route_batch = {}
        procs_by_line = {}
        if pedidos:
            all_existing_lines = self.env["control.pedido.line"].search([("pedido_id", "in", pedidos.ids)])
            # Prefetch de los campos que se leen dentro del loop. Sin esto, leer
            # barcodreo por fila forzaria fetch -> flush -> recompute repetido de
            # state/process del pedido (era O(K^2) por pedido).
            all_existing_lines.fetch(['pedido_id', 'route', 'batch', 'codpro', 'barcodreo'])
            for line in all_existing_lines:
                pedido_id = line.pedido_id.id
                existing_lines_by_pedido.setdefault(pedido_id, {})
                existing_by_route_batch.setdefault(pedido_id, {})
                full_key = (line.route, line.batch, line.codpro)
                rb_key = (line.route, line.batch)
                existing_lines_by_pedido[pedido_id].setdefault(full_key, self.env["control.pedido.line"])
                existing_lines_by_pedido[pedido_id][full_key] |= line
                existing_by_route_batch[pedido_id].setdefault(rb_key, self.env["control.pedido.line"])
                existing_by_route_batch[pedido_id][rb_key] |= line
            # Preload de procesos por linea (1 query) -> evita leer
            # target_line.proceso_ids por fila (cada lectura forzaba flush).
            all_procs = self.env['control.proceso.lines'].search([('pedido_line_id', 'in', all_existing_lines.ids)])
            all_procs.fetch(['pedido_line_id', 'barOrdLin'])
            for proc in all_procs:
                procs_by_line.setdefault(proc.pedido_line_id.id, {})[proc.barOrdLin] = proc
        conn = self._get_sql_connection()
        try:
            cursor = conn.cursor()
            rows = []
            sql_chunk = 900
            for i in range(0, len(nums), sql_chunk):
                nums_batch = nums[i:i + sql_chunk]
                placeholders = ",".join(["?"] * len(nums_batch))
                query = f"""
                WITH PedidoHDR AS (
                    SELECT bc.BarCod, bc.BarSer, bc.BarSerDsc, bc.BarCodReo, bc.BarCodPar, bc.BarItem2 AS Pedido, bc.BarItem4 AS Partida, bc.BarColNom as ColorCode, bc.BarNomCli as ColorName
                    FROM BARCAD bc WITH (NOLOCK) WHERE bc.BarItem2 IN ({placeholders})
                ),
                Kilos AS (
                    SELECT bp.BarCod, bp.BarCodReo, SUM(bp.BarPieKil) AS Kilos, COUNT(bp.BarCod) AS Rollos
                    FROM BARPIE bp WITH (NOLOCK) WHERE bp.BarCod IN (SELECT BarCod FROM PedidoHDR) GROUP BY bp.BarCod, bp.BarCodReo
                )
                SELECT h.Pedido, h.Partida, h.BarCod AS HojaDeRuta, h.BarCodReo, h.BarCodPar, h.BarSer, h.BarSerDsc, h.ColorCode, h.ColorName, ISNULL(k.Kilos, 0) AS PesoTotal, ISNULL(k.Rollos, 0) AS Rollos, fp.FasDsc AS Proceso_Ultimo,
                       CASE WHEN bf_last.BarFasDTF > '1753-01-01' AND bf_next.FasCod IS NOT NULL
                            THEN sp_next.area ELSE sp.area END AS Area,
                       bf_last.BarFasDTI AS FechaInicio, bf_last.BarFasDTF AS FechaFinal,
                       bf_last.BarOrdLin AS UltOrden,
                       bf_next.FasCod AS Proceso_Siguiente
                FROM PedidoHDR h JOIN Kilos k ON k.BarCod = h.BarCod AND k.BarCodReo = h.BarCodReo AND k.Kilos > 0 AND k.Rollos > 0
                OUTER APPLY (
                    SELECT TOP (1) bf.FasCod, bf.BarFasDTI, bf.BarFasDTF, bf.BarOrdLin FROM BARFAS bf WITH (NOLOCK)
                    WHERE bf.BarCod = h.BarCod AND bf.BarCodReo = h.BarCodReo AND ISNULL(bf.BarCodPar,'') = ISNULL(h.BarCodPar,'') AND bf.BarFasDTI > '1753-01-01'
                    ORDER BY bf.BarOrdLin DESC, bf.BarFasDTI DESC
                ) bf_last
                OUTER APPLY (
                    -- Siguiente proceso de la ruta (por BarOrdLin) despues del ultimo
                    -- iniciado. Si no existe, bf_last es el ultimo proceso.
                    SELECT TOP (1) bf2.FasCod, bf2.BarOrdLin FROM BARFAS bf2 WITH (NOLOCK)
                    WHERE bf2.BarCod = h.BarCod AND bf2.BarCodReo = h.BarCodReo AND ISNULL(bf2.BarCodPar,'') = ISNULL(h.BarCodPar,'')
                      AND bf2.BarOrdLin > bf_last.BarOrdLin
                    ORDER BY bf2.BarOrdLin ASC
                ) bf_next
                LEFT JOIN FASPRO fp WITH (NOLOCK) ON fp.FasCod = bf_last.FasCod
                LEFT JOIN estatus_reproceso sp WITH (NOLOCK) ON sp.fase = bf_last.FasCod
                LEFT JOIN estatus_reproceso sp_next WITH (NOLOCK) ON sp_next.fase = bf_next.FasCod
                ORDER BY h.Pedido, h.BarCod, h.BarCodReo, h.BarCodPar;
                """
                cursor.execute(query, *nums_batch)
                cols = [c[0] for c in cursor.description]
                rows.extend([dict(zip(cols, row)) for row in cursor.fetchall()])
            # Keep only the latest reprocess number for each logical partida line.
            latest_rows = {}
            for row in rows:
                dedup_key = (
                    _safe_str(row.get("Pedido")),
                    _safe_str(row.get("Partida")),
                    _safe_str(row.get("HojaDeRuta")),
                    _safe_str(row.get("BarSer")),
                )
                current = latest_rows.get(dedup_key)
                if not current or _barcodreo_rank(row.get("BarCodReo")) >= _barcodreo_rank(current.get("BarCodReo")):
                    latest_rows[dedup_key] = row
            rows = list(latest_rows.values())

            barcods = set()
            for r in rows:
                bc = _safe_str(r.get("HojaDeRuta"))
                if bc: barcods.add(bc)
            processes_by_valid_key = {}
            if barcods:
                unique_barcods = list(barcods)
                chunk_size = 1000
                for i in range(0, len(unique_barcods), chunk_size):
                    chunk = unique_barcods[i:i + chunk_size]
                    placeholders_bc = ",".join(["?"] * len(chunk))
                    q_procs = f"""
                        SELECT bf.BarCod, bf.BarOrdLin, bf.FasCod, bf.MaqCodBis, bf.BarFasDTI, bf.BarFasDTF, bf.BarCodReo, bf.BarCodPar, fp.FasDsc
                        FROM BARFAS bf WITH (NOLOCK)
                        LEFT JOIN FASPRO fp WITH (NOLOCK) ON fp.FasCod = bf.FasCod
                        WHERE bf.BarCod IN ({placeholders_bc}) ORDER BY bf.BarCod, bf.BarOrdLin
                    """
                    cursor.execute(q_procs, *chunk)
                    p_cols = [c[0] for c in cursor.description]
                    p_rows = [dict(zip(p_cols, row)) for row in cursor.fetchall()]
                    for pr in p_rows:
                        bc = _safe_str(pr.get("BarCod"))
                        bcreo = _safe_float(pr.get("BarCodReo")) or ''
                        bcpar = _safe_str(pr.get("BarCodPar")) or ''
                        key = (bc, bcreo, bcpar)
                        desc = _safe_str(pr.get("FasDsc")) or _safe_str(pr.get("FasCod"))
                        start = pr.get("BarFasDTI")
                        end = pr.get("BarFasDTF")
                        if start and start.year <= 1753: start = False
                        if end and end.year <= 1753: end = False
                        vals_proc = {
                            "barOrdLin": int(pr.get("BarOrdLin") or 0),
                            "fas_code": _safe_str(pr.get("FasCod")), "fasCod": desc, "maqCodBis": _safe_str(pr.get("MaqCodBis")),
                            "barFasDTI": start, "barFasDTF": end,
                        }
                        processes_by_valid_key.setdefault(key, []).append((0, 0, vals_proc))
        finally:
            conn.close()
        line_cmds_by_pedido = {}
        procesos_a_crear = []
        process_vals_to_create = []
        # Pre-cargar fas_code -> workcenter.name de Odoo para usar como area
        # en lugar del area legacy de estatus_reproceso (mas granular).
        next_fas_codes = {(_safe_str(r.get("Proceso_Siguiente")) or '').strip().upper() for r in rows}
        next_fas_codes.discard('')
        area_by_fas = {}
        if next_fas_codes:
            ops = self.env['mrp.routing.workcenter.operation'].sudo().search([
                ('fas_code', 'in', list(next_fas_codes)),
            ])
            for op in ops:
                if op.workcenter_id:
                    area_by_fas[(op.fas_code or '').strip().upper()] = op.workcenter_id.name
        Line = self.env["control.pedido.line"].with_context(_area_by_fas=area_by_fas)
        # Particiones (BarCodPar) de una misma partida colapsan en la misma
        # linea Odoo (route, batch, codpro). Representamos la partida por la
        # particion MENOS avanzada (menor UltOrden = ultima fase iniciada mas
        # atras): la partida no esta lista hasta que TODAS sus particiones
        # terminen. Sin esto ganaba la particion grabada de ultimo (no
        # determinista), y una sub-partida adelantada ocultaba el atraso real.
        def _line_key_of(dr):
            return (
                _safe_str(dr.get("HojaDeRuta")),
                _safe_str(dr.get("Partida")) or '',
                _safe_str(dr.get("BarSer"))[1:] or '',
            )
        def _progress_of(dr):
            v = dr.get("UltOrden")
            return int(v) if v is not None else 0
        _rep_by_key = {}
        for _dr in rows:
            _k = _line_key_of(_dr)
            _cur = _rep_by_key.get(_k)
            # Empate: gana el primero (BarCodPar en blanco ordena antes que 'A',
            # i.e. la particion principal).
            if _cur is None or _progress_of(_dr) < _progress_of(_cur):
                _rep_by_key[_k] = _dr
        rows = list(_rep_by_key.values())
        # Preload producto + lab.dev (elimina los 2 N+1 por fila de _vals_from_det_row).
        codpros = {(_safe_str(dr.get("BarSer")) or '')[1:] for dr in rows}
        codpros.discard('')
        product_by_code = {}
        if codpros:
            for p in self.env['product.template'].sudo().search([('default_code', 'in', list(codpros))]):
                product_by_code.setdefault(p.default_code, p.id)
        colorcodes = {c for c in (_safe_str(dr.get("ColorCode")) for dr in rows) if c}
        lab_by_color = {}
        if colorcodes:
            for lab in self.env['lab.dev.line'].sudo().search([('color_code', 'in', list(colorcodes))]):
                lab_by_color.setdefault(lab.color_code, lab.id)
        Line = Line.with_context(_product_by_code=product_by_code, _lab_by_color=lab_by_color)
        zombie_proc_ids = []
        for dr in rows:
            num = _safe_str(dr.get("Pedido"))
            pedido = existing_map.get(num)
            if not pedido: continue
            vals_line = Line._vals_from_det_row(dr)
            bc = _safe_str(dr.get("HojaDeRuta"))
            bcreo = _safe_float(dr.get("BarCodReo")) or ''
            bcpar = _safe_str(dr.get("BarCodPar")) or ''
            key = (bc, bcreo, bcpar)
            if key in processes_by_valid_key: vals_line["proceso_ids"] = processes_by_valid_key[key]
            line_key = (vals_line.get("route"), vals_line.get("batch"), vals_line.get("codpro"))
            existing_lines = existing_lines_by_pedido.get(pedido.id, {}).get(line_key)
            if not existing_lines:
                # Fallback: linea creada en sync anterior con un codpro distinto
                # (vacio o con la 'P' inicial antes de aplicarse [1:]). La
                # actualizamos in-place en vez de crear una duplicada zombie.
                rb_key = (vals_line.get("route"), vals_line.get("batch"))
                existing_lines = existing_by_route_batch.get(pedido.id, {}).get(rb_key)
            if existing_lines:
                target_line = existing_lines.sorted(
                    key=lambda l: (_barcodreo_rank(l.barcodreo), l.id),
                    reverse=True,
                )[:1]
                write_vals = {
                    'product_id': vals_line.get('product_id'),
                    'lab_dev_line_id': vals_line.get('lab_dev_line_id'),
                    'codpro': vals_line.get('codpro'),
                    'rollos': vals_line.get('rollos'),
                    'kilograms': vals_line.get('kilograms'),
                    'process': vals_line.get('process'),
                    'area': vals_line.get('area'),
                    'start_date': vals_line.get('start_date'),
                    'end_date': vals_line.get('end_date'),
                    'barcodreo': vals_line.get('barcodreo'),
                    'description': vals_line.get('description'),
                    'colorcode': vals_line.get('colorcode'),
                    'colorname': vals_line.get('colorname'),
                }
                # Keep existing rows but normalize all of them to newest data/barcodreo.
                existing_lines.write(write_vals)

                if "proceso_ids" in vals_line and vals_line["proceso_ids"]:
                    existing_procs = procs_by_line.get(target_line.id, {})
                    new_ordlines = {cmd[2].get('barOrdLin') for cmd in vals_line["proceso_ids"]}
                    for cmd in vals_line["proceso_ids"]:
                        vals_proc = cmd[2].copy()
                        vals_proc['pedido_line_id'] = target_line.id
                        proc_key = vals_proc.get('barOrdLin')
                        if proc_key in existing_procs: existing_procs[proc_key].write(vals_proc)
                        else: process_vals_to_create.append(vals_proc)
                    # Borrar procesos huerfanos: existen en Odoo pero ya no en
                    # TEXPLUS para esta (BarCod, BarCodReo). Se acumulan y se
                    # borran en lote al final (unlink por fila forzaba flush).
                    zombie_proc_ids.extend(
                        proc.id for ord_lin, proc in existing_procs.items()
                        if ord_lin not in new_ordlines)
            else:
                procesos_temp = vals_line.pop("proceso_ids", None)
                line_cmds_by_pedido.setdefault(pedido.id, []).append((0, 0, vals_line))
                if procesos_temp: procesos_a_crear.append((pedido.id, line_key, procesos_temp))
        for pid, cmds in line_cmds_by_pedido.items(): self.browse(pid).write({"line_ids": cmds})
        if zombie_proc_ids:
            self.env['control.proceso.lines'].browse(zombie_proc_ids).unlink()
        if procesos_a_crear:
            created_lines = self.env["control.pedido.line"].search([("pedido_id", "in", list(line_cmds_by_pedido.keys()))])
            created_lines_map = {(l.pedido_id.id, l.route, l.barcodreo, l.batch): l for l in created_lines}
            for pedido_id, line_key, procesos_list in procesos_a_crear:
                new_line = created_lines_map.get((pedido_id, line_key[0], line_key[1], line_key[2]))
                if not new_line:
                    continue
                for cmd in procesos_list:
                    vals_proc = cmd[2].copy()
                    vals_proc['pedido_line_id'] = new_line.id
                    process_vals_to_create.append(vals_proc)
        if process_vals_to_create:
            self.env['control.proceso.lines'].create(process_vals_to_create)
        # Un solo flush -> recompute de state/process/etc. UNA vez (no por fila).
        self.env.flush_all()
        self._sync_ctrl_info_reprocesos(list(existing_map.values()) + list(self.env['control.pedido'].browse(line_cmds_by_pedido.keys())))
        self._cleanup_zombie_lines(rows, existing_map)
        # Punto de extensión: módulos como idtx_printing_dbf lo sobreescriben
        # para enriquecer los pedidos sincronizados con datos derivados de
        # SITPRO (p.ej. el kilaje de estampado). Un fallo aquí no debe abortar
        # el sync principal de pedidos.
        try:
            self._sync_extra_data(nums)
        except Exception:
            _logger.exception("sync_from_dbf: fallo el hook _sync_extra_data")
        _logger.info("sync_from_dbf: %s creados, %s actualizados en %.1fs",
                     created, updated, time.perf_counter() - _sync_t0)
        return {"created": created, "updated": updated}

    def _sync_extra_data(self, nums):
        """Hook llamado al final de sync_from_dbf con la lista de números de
        pedido procesados (`nums`). Los módulos que derivan datos adicionales
        de SITPRO lo extienden — ver idtx_printing_dbf, que calcula el kilaje
        de estampado por pedido.

        Aquí refresca los kilos del reporte 'Kilos x Pesar' (tinto_acab vs
        alm_acab_ing en SITPRO SQL). El caller ya envuelve en try/except."""
        self.env['control.pedido.line'].refresh_kilos_pesar()

    def _cleanup_zombie_lines(self, rows, existing_map):
        """Borra lineas Odoo cuya combinacion (pedido, route, batch) ya no
        existe en TEXPLUS. Aparecen cuando una partida es anulada/movida en
        TEXPLUS a otra hoja de ruta o pedido distinto: la linea original
        queda huérfana porque el sync solo agrega/actualiza, nunca borra
        lo que ya no aparece.

        Antes de borrar, las evaluaciones de tono (`control.tono.eval.group.line`)
        de la zombie se reasignan a la 'gemela' del mismo batch (si existe),
        para no perder datos de calidad.

        Solo limpia pedidos confirmados (que devolvieron al menos una fila
        TEXPLUS); pedidos sin datos quedan intactos para evitar borrados
        accidentales cuando hay errores transitorios de la conexion.
        """
        valid_keys_by_pedido = {}
        for row in rows:
            pedido_num = _safe_str(row.get("Pedido"))
            pedido = existing_map.get(pedido_num)
            if not pedido:
                continue
            route = _safe_str(row.get("HojaDeRuta"))
            batch = _safe_str(row.get("Partida")) or ''
            if route and batch:
                valid_keys_by_pedido.setdefault(pedido.id, set()).add((route, batch))

        if not valid_keys_by_pedido:
            return

        Line = self.env['control.pedido.line']
        zombies = Line.browse()
        for pedido_id, valid_keys in valid_keys_by_pedido.items():
            odoo_lines = Line.search([
                ('pedido_id', '=', pedido_id),
                ('batch', '!=', False), ('batch', '!=', ''),
                ('route', '!=', False), ('route', '!=', ''),
            ])
            for line in odoo_lines:
                if (line.route, line.batch) not in valid_keys:
                    zombies |= line

        if not zombies:
            return

        # Reasignar tono evals a la gemela del mismo batch en otro pedido
        # (la sincronizada actualmente con TEXPLUS).
        keeper_by_zombie = {}
        for zombie in zombies:
            keeper = Line.search([
                ('id', 'not in', zombies.ids),
                ('batch', '=', zombie.batch),
            ], limit=1)
            if keeper:
                keeper_by_zombie[zombie.id] = keeper.id

        if keeper_by_zombie:
            TonoLine = self.env['control.tono.eval.group.line'].sudo()
            evals = TonoLine.search([('pedido_line_id', 'in', list(keeper_by_zombie.keys()))])
            for ev in evals:
                new_id = keeper_by_zombie.get(ev.pedido_line_id.id)
                if new_id and ev.pedido_line_id.id != new_id:
                    ev.pedido_line_id = new_id

        # Las zombies sin keeper aun pueden tener tono evals u otros FKs
        # apuntando a ellas (eval.group.line.pedido_line_id_fkey). No las
        # borramos: preservar data > exactitud del catalogo. Las con keeper
        # ya tienen sus evals reasignadas y deberian poder borrarse.
        zombies_with_keeper = zombies.filtered(lambda z: z.id in keeper_by_zombie)
        zombies_without_keeper = zombies - zombies_with_keeper

        _logger.info(
            "sync_from_dbf: cleanup zombie lines = %s (con keeper = %s, sin keeper = %s)",
            len(zombies), len(zombies_with_keeper), len(zombies_without_keeper),
        )
        if zombies_without_keeper:
            _logger.warning(
                "sync_from_dbf: %s zombies sin keeper se preservan para no romper FKs externas (ids=%s, batches=%s)",
                len(zombies_without_keeper),
                zombies_without_keeper.ids[:20],
                zombies_without_keeper.mapped('batch')[:20],
            )

        if not zombies_with_keeper:
            return
        # Un fallo aqui (p.ej. otra FK no contemplada) no debe abortar el
        # sync entero — el cleanup es cosmetico, el sync real (fases,
        # ctrl_info) es prioritario. Usamos savepoint para que un rollback
        # NO descarte el resto del trabajo de sync_from_dbf.
        try:
            with self.env.cr.savepoint(flush=False):
                zombies_with_keeper.unlink()
        except Exception:
            _logger.warning(
                "sync_from_dbf: unlink de %s zombies con keeper fallo, "
                "se omite el cleanup en esta corrida (ids=%s)",
                len(zombies_with_keeper), zombies_with_keeper.ids[:20],
                exc_info=True,
            )

    def _sync_ctrl_info_reprocesos(self, pedidos):
        """Pull motivo/area from SQL Server `ctrl_info` and apply to lines.

        A report is matched by partida AND ruta: `ctrl_info.correlvouc` against
        `control.pedido.line.batch`, and `ctrl_info.numot` against
        `control.pedido.line.route`. Only open (ACTIVO=0) REPROCESO/REPOSICION
        records from years after 2023 are considered.
        """
        pedido_ids = {p.id for p in pedidos if p}
        if not pedido_ids:
            return
        lines = self.env['control.pedido.line'].search([
            ('pedido_id', 'in', list(pedido_ids)),
            ('batch', '!=', False),
            ('route', '!=', False),
        ])
        if not lines:
            return
        pairs = {(l.batch, l.route) for l in lines if l.batch and l.route}
        info_map = self._fetch_ctrl_info_reprocesos(pairs)
        # Group writes: same value tuple → single bulk write.
        Line = self.env['control.pedido.line']
        by_vals = {}
        for line in lines:
            info = info_map.get((line.batch, line.route))
            key = (
                (info or {}).get('motivo1') or False,
                (info or {}).get('area1') or False,
                (info or {}).get('report_date') or False,
                (info or {}).get('to_reprocess') or 0.0,
                (info or {}).get('obsctrl') or False,
                (info or {}).get('motivo') or False,
            )
            by_vals[key] = by_vals.get(key, Line) | line
        for (motivo1, area, report_date, to_reprocess, obsctrl, motivo), recs in by_vals.items():
            recs.write({
                'motivo': motivo,
                'motivo1': motivo1,
                'area1': area,
                'report_date': report_date,
                'to_reprocess': to_reprocess,
                'obsctrl': obsctrl,
            })

    def _fetch_ctrl_info_reprocesos(self, pairs):
        """Return {(correlvouc, numot): {...}} from ctrl_info.

        `pairs` is an iterable of (batch, route) tuples. SQL columns:
        correlvouc (joins to batch), numot (joins to route), motivo1, area1,
        fecinfo (fecha del informe), ACTIVO, kneto.
        Filters: YEAR(fecinfo) > 2023, ACTIVO = 0, motivo IN (REPROCESO, REPOSICION).
        When several reports match the same (partida, ruta) the most recent
        fecinfo wins.
        """
        pairs = [(b, r) for b, r in pairs if b and r]
        if not pairs:
            return {}
        wanted = {(_safe_str(b).strip(), _safe_str(r).strip()) for b, r in pairs}
        # Query a superset by the distinct batches and routes, then keep only
        # the rows whose (correlvouc, numot) is an actually requested pair.
        # SQL Server has no clean tuple-IN, and over-fetching here is cheap.
        batches = sorted({b for b, _ in wanted})
        routes = sorted({r for _, r in wanted})
        try:
            conn = self._get_sitpro_connection()
        except Exception:
            return {}
        out = {}
        try:
            cursor = conn.cursor()
            chunk = 900
            for i in range(0, len(batches), chunk):
                batch_chunk = batches[i:i + chunk]
                # correlvouc / numot are CHAR(n) columns padded with trailing
                # spaces; RTRIM on the column side keeps the IN tolerant.
                b_placeholders = ",".join(["?"] * len(batch_chunk))
                for j in range(0, len(routes), chunk):
                    route_chunk = routes[j:j + chunk]
                    r_placeholders = ",".join(["?"] * len(route_chunk))
                    cursor.execute(
                        f"""
                        SELECT correlvouc, numot, motivo, motivo1, area1, fecinfo, kneto, obsctrl
                        FROM ctrl_info WITH (NOLOCK)
                        WHERE YEAR(fecinfo) > 2023
                          AND ACTIVO = 0
                          AND motivo IN ('REPROCESO', 'REPOSICION')
                          AND LTRIM(RTRIM(correlvouc)) IN ({b_placeholders})
                          AND LTRIM(RTRIM(numot)) IN ({r_placeholders})
                        ORDER BY correlvouc, numot, fecinfo DESC
                        """,
                        *batch_chunk, *route_chunk,
                    )
                    # fecinfo viene de SQL Server como datetime NAIVE en hora
                    # local de Peru. Si lo guardamos directo en Odoo (que
                    # asume UTC), pierde 5h y el dia se desplaza. Lo
                    # convertimos a UTC explicitamente.
                    pe_tz = pytz.timezone('America/Lima')
                    for correlvouc, numot, motivo, motivo1, area1, fecha, kneto, obsctrl in cursor.fetchall():
                        key = (_safe_str(correlvouc).strip(), _safe_str(numot).strip())
                        if key in wanted and key not in out:  # first row per pair = newest
                            out[key] = {
                                'motivo': _safe_str(motivo) or False,
                                'motivo1': _safe_str(motivo1),
                                'area1': _safe_str(area1),
                                'report_date': _safe_date(fecha, pe_tz) or False,
                                'to_reprocess': _safe_float(kneto),
                                'obsctrl': (_safe_str(obsctrl) or '').strip() or False,
                            }
        finally:
            conn.close()
        return out

    def action_sync_from_dbf(self):
        self.sync_master_data()
        self.sync_operators()
        res = self.sync_from_dbf()
        return {"type": "ir.actions.client", "tag": "display_notification", "params": {"title": "FoxPro → Odoo", "message": f"Creados: {res['created']} | Actualizados: {res['updated']}", "sticky": False}}

    def sync_closed_pedidos_once(self):
        """One-shot: refresca lineas de pedidos cerrados (is_active=False)
        con los datos actuales de TEXPLUS. Util para corregir areas/procesos
        que quedaron congelados con el estado de antes del cierre del pedido.

        Re-ejecuta la query principal del cron sin filtrar por activos.
        Solo ACTUALIZA lineas existentes (no crea ni borra). Tampoco toca
        el flag is_active del pedido.

        Pensado para correr UNA VEZ desde shell, no como cron periodico.
        """
        pedidos = self.search([('is_active', '=', False)])
        nums = [p.numordped for p in pedidos if p.numordped]
        if not nums:
            return {"updated": 0}
        _logger.info("sync_closed_pedidos_once: procesando %s pedidos inactivos", len(nums))
        existing_map = {p.numordped: p for p in pedidos}

        existing_lines_by_pedido = {}
        existing_by_route_batch = {}
        for line in self.env['control.pedido.line'].search([('pedido_id', 'in', pedidos.ids)]):
            pedido_id = line.pedido_id.id
            existing_lines_by_pedido.setdefault(pedido_id, {})
            existing_by_route_batch.setdefault(pedido_id, {})
            full_key = (line.route, line.batch, line.codpro)
            rb_key = (line.route, line.batch)
            existing_lines_by_pedido[pedido_id].setdefault(full_key, self.env['control.pedido.line'])
            existing_lines_by_pedido[pedido_id][full_key] |= line
            existing_by_route_batch[pedido_id].setdefault(rb_key, self.env['control.pedido.line'])
            existing_by_route_batch[pedido_id][rb_key] |= line

        conn = self._get_sql_connection()
        rows = []
        try:
            cursor = conn.cursor()
            sql_chunk = 900
            for i in range(0, len(nums), sql_chunk):
                nums_batch = nums[i:i + sql_chunk]
                placeholders = ",".join(["?"] * len(nums_batch))
                query = f"""
                WITH PedidoHDR AS (
                    SELECT bc.BarCod, bc.BarSer, bc.BarSerDsc, bc.BarCodReo, bc.BarCodPar, bc.BarItem2 AS Pedido, bc.BarItem4 AS Partida, bc.BarColNom as ColorCode, bc.BarNomCli as ColorName
                    FROM BARCAD bc WITH (NOLOCK) WHERE bc.BarItem2 IN ({placeholders})
                ),
                Kilos AS (
                    SELECT bp.BarCod, bp.BarCodReo, SUM(bp.BarPieKil) AS Kilos, COUNT(bp.BarCod) AS Rollos
                    FROM BARPIE bp WITH (NOLOCK) WHERE bp.BarCod IN (SELECT BarCod FROM PedidoHDR) GROUP BY bp.BarCod, bp.BarCodReo
                )
                SELECT h.Pedido, h.Partida, h.BarCod AS HojaDeRuta, h.BarCodReo, h.BarCodPar, h.BarSer, h.BarSerDsc, h.ColorCode, h.ColorName, ISNULL(k.Kilos, 0) AS PesoTotal, ISNULL(k.Rollos, 0) AS Rollos, fp.FasDsc AS Proceso_Ultimo,
                       CASE WHEN bf_last.BarFasDTF > '1753-01-01' AND bf_next.FasCod IS NOT NULL
                            THEN sp_next.area ELSE sp.area END AS Area,
                       bf_last.BarFasDTI AS FechaInicio, bf_last.BarFasDTF AS FechaFinal,
                       bf_last.BarOrdLin AS UltOrden,
                       bf_next.FasCod AS Proceso_Siguiente
                FROM PedidoHDR h JOIN Kilos k ON k.BarCod = h.BarCod AND k.BarCodReo = h.BarCodReo AND k.Kilos > 0 AND k.Rollos > 0
                OUTER APPLY (
                    SELECT TOP (1) bf.FasCod, bf.BarFasDTI, bf.BarFasDTF, bf.BarOrdLin FROM BARFAS bf WITH (NOLOCK)
                    WHERE bf.BarCod = h.BarCod AND bf.BarCodReo = h.BarCodReo AND ISNULL(bf.BarCodPar,'') = ISNULL(h.BarCodPar,'') AND bf.BarFasDTI > '1753-01-01'
                    ORDER BY bf.BarOrdLin DESC, bf.BarFasDTI DESC
                ) bf_last
                OUTER APPLY (
                    SELECT TOP (1) bf2.FasCod, bf2.BarOrdLin FROM BARFAS bf2 WITH (NOLOCK)
                    WHERE bf2.BarCod = h.BarCod AND bf2.BarCodReo = h.BarCodReo AND ISNULL(bf2.BarCodPar,'') = ISNULL(h.BarCodPar,'')
                      AND bf2.BarOrdLin > bf_last.BarOrdLin
                    ORDER BY bf2.BarOrdLin ASC
                ) bf_next
                LEFT JOIN FASPRO fp WITH (NOLOCK) ON fp.FasCod = bf_last.FasCod
                LEFT JOIN estatus_reproceso sp WITH (NOLOCK) ON sp.fase = bf_last.FasCod
                LEFT JOIN estatus_reproceso sp_next WITH (NOLOCK) ON sp_next.fase = bf_next.FasCod
                """
                cursor.execute(query, *nums_batch)
                cols = [c[0] for c in cursor.description]
                rows.extend([dict(zip(cols, row)) for row in cursor.fetchall()])

            # Procesos detalle por (BarCod, BarCodReo, BarCodPar) — para
            # validar y limpiar procesos huerfanos en Odoo.
            barcods = {_safe_str(r.get("HojaDeRuta")) for r in rows if r.get("HojaDeRuta")}
            barcods.discard('')
            processes_by_valid_key = {}
            if barcods:
                bc_list = list(barcods)
                for i in range(0, len(bc_list), 1000):
                    chunk = bc_list[i:i + 1000]
                    placeholders_bc = ",".join(["?"] * len(chunk))
                    cursor.execute(
                        f"""SELECT bf.BarCod, bf.BarOrdLin, bf.BarCodReo, bf.BarCodPar
                            FROM BARFAS bf WITH (NOLOCK)
                            WHERE bf.BarCod IN ({placeholders_bc})""",
                        *chunk,
                    )
                    for bc, ordlin, bcreo, bcpar in cursor.fetchall():
                        k = (_safe_str(bc), _safe_float(bcreo) or '', _safe_str(bcpar) or '')
                        processes_by_valid_key.setdefault(k, set()).add(int(ordlin or 0))
        finally:
            conn.close()

        latest_rows = {}
        for row in rows:
            key = (_safe_str(row.get("Pedido")), _safe_str(row.get("Partida")),
                   _safe_str(row.get("HojaDeRuta")), _safe_str(row.get("BarSer")))
            current = latest_rows.get(key)
            if not current or _barcodreo_rank(row.get("BarCodReo")) >= _barcodreo_rank(current.get("BarCodReo")):
                latest_rows[key] = row
        rows = list(latest_rows.values())

        # Pre-cargar fas_code -> workcenter.name de Odoo (idem sync_from_dbf).
        next_fas_codes = {(_safe_str(r.get("Proceso_Siguiente")) or '').strip().upper() for r in rows}
        next_fas_codes.discard('')
        area_by_fas = {}
        if next_fas_codes:
            ops = self.env['mrp.routing.workcenter.operation'].sudo().search([
                ('fas_code', 'in', list(next_fas_codes)),
            ])
            for op in ops:
                if op.workcenter_id:
                    area_by_fas[(op.fas_code or '').strip().upper()] = op.workcenter_id.name
        Line = self.env['control.pedido.line'].with_context(_area_by_fas=area_by_fas)
        updated = 0
        for dr in rows:
            num = _safe_str(dr.get("Pedido"))
            pedido = existing_map.get(num)
            if not pedido:
                continue
            vals_line = Line._vals_from_det_row(dr)
            full_key = (vals_line.get("route"), vals_line.get("batch"), vals_line.get("codpro"))
            existing_lines = existing_lines_by_pedido.get(pedido.id, {}).get(full_key)
            if not existing_lines:
                rb_key = (vals_line.get("route"), vals_line.get("batch"))
                existing_lines = existing_by_route_batch.get(pedido.id, {}).get(rb_key)
            if not existing_lines:
                continue
            write_vals = {
                'codpro': vals_line.get('codpro'),
                'rollos': vals_line.get('rollos'),
                'kilograms': vals_line.get('kilograms'),
                'process': vals_line.get('process'),
                'area': vals_line.get('area'),
                'start_date': vals_line.get('start_date'),
                'end_date': vals_line.get('end_date'),
                'barcodreo': vals_line.get('barcodreo'),
                'description': vals_line.get('description'),
                'colorcode': vals_line.get('colorcode'),
                'colorname': vals_line.get('colorname'),
                'product_id': vals_line.get('product_id'),
                'lab_dev_line_id': vals_line.get('lab_dev_line_id'),
            }
            existing_lines.write(write_vals)
            updated += len(existing_lines)
            # Limpiar procesos huerfanos para cada linea: procesos en Odoo
            # cuyo BarOrdLin no esta en TEXPLUS para esa (BarCod, BarCodReo).
            bc = _safe_str(dr.get("HojaDeRuta"))
            bcreo = _safe_float(dr.get("BarCodReo")) or ''
            bcpar = _safe_str(dr.get("BarCodPar")) or ''
            valid_ordlines = processes_by_valid_key.get((bc, bcreo, bcpar), set())
            for line in existing_lines:
                zombies = line.proceso_ids.filtered(lambda p: p.barOrdLin not in valid_ordlines)
                if zombies:
                    zombies.unlink()
        # Tambien refresca motivo/area de reproceso y kilos a reprocesar
        # desde SITPRO ctrl_info para los pedidos cerrados (cuando esos
        # datos fueron completados despues del cierre del pedido).
        self._sync_ctrl_info_reprocesos(pedidos)
        _logger.info("sync_closed_pedidos_once: actualizadas %s lineas", updated)
        return {"updated": updated}

    def sync_master_data(self):
        conn = self._get_sql_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT FasCod, FasDsc, MaqCod FROM FASPRO WITH (NOLOCK)")
            for row in cursor.fetchall():
                code, name, def_maq = _safe_str(row[0]), _safe_str(row[1]), _safe_str(row[2])
                if not code: continue
                existing_def = self.env['control.faspro.definition'].sudo().search([('code', '=', code)], limit=1)
                vals_def = {'name': name or code, 'default_maq_code': def_maq}
                if existing_def: existing_def.write(vals_def)
                else: self.env['control.faspro.definition'].sudo().create({'code': code, **vals_def})
                operation = self.env['mrp.routing.workcenter.operation'].sudo().search(['|', ('fas_code', '=', code), ('name', '=', name)], limit=1)
                if operation:
                    operation.write({'fas_code': code})
                    if def_maq and not operation.workcenter_id:
                        wc = self.env['mrp.workcenter'].sudo().search([('code', '=', def_maq)], limit=1)
                        if wc: operation.write({'workcenter_id': wc.id})
        finally:
            conn.close()

    def sync_operators(self):
        conn = self._get_sql_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT OpeCod, OpeNom FROM OPERAR WITH (NOLOCK)")
            for row in cursor.fetchall():
                code, name = _safe_str(row[0]), _safe_str(row[1])
                if not code: continue
                existing = self.env['control.operator'].sudo().search([('code', '=', code)], limit=1)
                vals = {'name': name or code}
                if existing: existing.write(vals)
                else: self.env['control.operator'].sudo().create({'code': code, **vals})
        finally:
            conn.close()
