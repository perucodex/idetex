# -*- coding: utf-8 -*-
from dbf import Char
import datetime
import logging
import pyodbc
pyodbc.setDecimalSeparator(".")
from odoo import models, fields, api, _
from odoo.exceptions import UserError
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
    _order = "num_days desc, state desc, fecoc desc, numordped desc"
    _rec_name = 'numordped'

    fecha = fields.Date(string="Order Date")
    fecoc = fields.Date(string="Customer Order Date")
    numordped = fields.Char(string="Order Number", required=True, index=True)
    customer = fields.Char('Customer')
    # salesman = fields.Char('Salesman')
    # cdgven = fields.Char('Salesman Code')
    user_id = fields.Many2one('res.users', string='Salesman')
    tipoventa = fields.Char(string="Type of Sale")
    total_weight = fields.Float('Total Weight')
    produced_weight = fields.Float('Produced Weight')
    line_ids = fields.One2many("control.pedido.line", "pedido_id", string="Detail")
    process = fields.Char('Process', compute='_compute_process', store=True)
    area = fields.Char('Area', compute='_compute_process', store=True)
    is_active = fields.Boolean('is_active?')
    num_days = fields.Integer('Number of Days', compute='_compute_num_days', store=True)
    state = fields.Selection([
        ('on', 'On Time'),
        ('de', 'Delayed'),
        ('do', 'Done'),
        ('se', 'Settled'),
    ], string='State', compute='_compute_state', default='on', store=True, tracking=True)

    _product_code_unique = models.Constraint('unique(numordped)', "Ya existe un pedido con ese Número de Orden!")

    @api.depends('fecoc')
    def _compute_num_days(self):
        today = fields.Date.context_today(self)
        for rec in self:
            if not rec.fecoc:
                rec.num_days = 0
                continue
            days = 0
            current = rec.fecoc
            while current <= today:
                if current.weekday() != 6:
                    days += 1
                current += datetime.timedelta(days=1)
            rec.num_days = days

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

    def settle_order(self):
        res = _settle_order_dbf("/mnt/fox/sit06/dbf/vta_cab_pedido.dbf", self.numordped, not self.is_active)
        if res:
            new_active = not self.is_active
            self.is_active = new_active
            # Propagar al estado de las lineas:
            # - Liquidacion (is_active False -> state='se'): lineas a 'completed'.
            # - Reversion (is_active True): lineas vuelven a 'active'.
            line_state = 'active' if new_active else 'completed'
            self.line_ids.write({'state': line_state})
        return res

    def _get_sql_connection(self):
        try:
            conn = pyodbc.connect(
                "DSN=ENBTEX1_DSN;PORT=1433;UID=sistemas;PWD=idtE#21@IRdc95;TDS_Version=7.3;"
            )
            return conn
        except Exception as e:
            raise UserError(f"No se pudo conectar a SQL Server: {e}")

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
        cab_by_num = {}
        nums = []
        nums_seen = set()
        nums_to_settle = []
        for rec in _iter_dbf("/mnt/fox/sit06/dbf/vta_cab_pedido.dbf"):
            fecha = rec["FECHA"]
            if not fecha or fecha < datetime.date(2025, 6, 30):
                continue
            if not _safe_bool(rec["ACTIVO"]):
                num = _safe_str(rec["NUMORDPED"])
                if num:
                    nums_to_settle.append(num)
                continue
            # if _safe_str(rec["TIPOVENTA"][:10]) != "VENTA DE T":
            #     continue
            num = _safe_str(rec["NUMORDPED"])
            if not num:
                continue
            if num not in nums_seen:
                nums_seen.add(num)
                nums.append(num)
            cab_by_num[num] = {
                "fecha": _safe_date(rec["FECHA"]),
                "fecoc": _safe_date(rec["FECOC"]),
                "customer": _safe_str(rec["RAZSOC"]),
                # "salesman": _safe_str(rec["USUARIO"]),
                # "cdgven": _safe_str(rec["CDGVEN"]),
                "user_id": self.env['res.users'].search([('vendor_code_sitpro', '=', _safe_str(rec["CDGVEN"]))], limit=1).id,
                "tipoventa": _safe_str(rec["TIPOVENTA"]),
                "total_weight": _safe_float(rec["TOTKIL"]),
                "is_active": _safe_bool(rec["ACTIVO"]),
            }
            # if num.strip() == '00434-26':
            # import logging
            # logging.getLogger(__name__).info(f"Debug sync: {num}")
        # Cierre suave: pedidos que estaban activos en Odoo y acaban de
        # cerrarse en SITPRO (ACTIVO=False en DBF) se sincronizan UNA ULTIMA
        # VEZ antes de marcarlos inactivos. Asi su estado final (areas,
        # procesos, fechas) queda congelado limpio. Sin esto, se quedaban con
        # el estado de la corrida anterior - tipico caso: area=ACABADO cuando
        # ya tenian CALIDAD como next process.
        if nums_to_settle:
            recently_closed = self.search([
                ('numordped', 'in', list(set(nums_to_settle))),
                ('is_active', '=', True),
            ])
            for rec in recently_closed:
                num = rec.numordped
                if num and num not in nums_seen:
                    nums_seen.add(num)
                    nums.append(num)
                    cab_by_num[num] = {
                        'fecha': rec.fecha,
                        'fecoc': rec.fecoc,
                        'customer': rec.customer or '',
                        'user_id': rec.user_id.id if rec.user_id else False,
                        'tipoventa': rec.tipoventa or '',
                        'total_weight': rec.total_weight or 0.0,
                        'is_active': False,  # queda inactivo despues del refresh
                    }

        if not nums:
            return {"created": 0, "updated": 0}

        settle_chunk = 2000
        for i in range(0, len(nums_to_settle), settle_chunk):
            settle_batch = nums_to_settle[i:i + settle_chunk]
            self.search([("numordped", "in", settle_batch)]).write({"is_active": False})
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
        if pedidos:
            for line in self.env["control.pedido.line"].search([("pedido_id", "in", pedidos.ids)]):
                pedido_id = line.pedido_id.id
                existing_lines_by_pedido.setdefault(pedido_id, {})
                existing_by_route_batch.setdefault(pedido_id, {})
                full_key = (line.route, line.batch, line.codpro)
                rb_key = (line.route, line.batch)
                existing_lines_by_pedido[pedido_id].setdefault(full_key, self.env["control.pedido.line"])
                existing_lines_by_pedido[pedido_id][full_key] |= line
                existing_by_route_batch[pedido_id].setdefault(rb_key, self.env["control.pedido.line"])
                existing_by_route_batch[pedido_id][rb_key] |= line
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
        for dr in rows:
            num = _safe_str(dr.get("Pedido"))
            pedido = existing_map.get(num)
            if not pedido: continue
            vals_line = self.env["control.pedido.line"]._vals_from_det_row(dr)
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
                }
                # Keep existing rows but normalize all of them to newest data/barcodreo.
                existing_lines.write(write_vals)

                if "proceso_ids" in vals_line and vals_line["proceso_ids"]:
                    existing_procs = {proc.barOrdLin: proc for proc in target_line.proceso_ids}
                    for cmd in vals_line["proceso_ids"]:
                        vals_proc = cmd[2].copy()
                        vals_proc['pedido_line_id'] = target_line.id
                        proc_key = vals_proc.get('barOrdLin')
                        if proc_key in existing_procs: existing_procs[proc_key].write(vals_proc)
                        else: process_vals_to_create.append(vals_proc)
            else:
                procesos_temp = vals_line.pop("proceso_ids", None)
                line_cmds_by_pedido.setdefault(pedido.id, []).append((0, 0, vals_line))
                if procesos_temp: procesos_a_crear.append((pedido.id, line_key, procesos_temp))
        for pid, cmds in line_cmds_by_pedido.items(): self.browse(pid).write({"line_ids": cmds})
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
        self._sync_ctrl_info_reprocesos(list(existing_map.values()) + list(self.env['control.pedido'].browse(line_cmds_by_pedido.keys())))
        self._cleanup_zombie_lines(rows, existing_map)
        return {"created": created, "updated": updated}

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

        _logger.info(
            "sync_from_dbf: cleanup zombie lines = %s (re-asignadas %s evaluaciones de tono)",
            len(zombies), len(keeper_by_zombie),
        )
        zombies.unlink()

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
            )
            by_vals[key] = by_vals.get(key, Line) | line
        for (motivo, area, report_date, to_reprocess), recs in by_vals.items():
            recs.write({
                'motivo1': motivo,
                'area1': area,
                'report_date': report_date,
                'to_reprocess': to_reprocess,
            })

    def _fetch_ctrl_info_reprocesos(self, pairs):
        """Return {(correlvouc, numot): {...}} from ctrl_info.

        `pairs` is an iterable of (batch, route) tuples. SQL columns:
        correlvouc (joins to batch), numot (joins to route), motivo1, area1,
        FECHA, ACTIVO, kneto.
        Filters: YEAR(FECHA) > 2023, ACTIVO = 0, motivo IN (REPROCESO, REPOSICION).
        When several reports match the same (partida, ruta) the most recent
        FECHA wins.
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
                        SELECT correlvouc, numot, motivo1, area1, FECHA, kneto
                        FROM ctrl_info WITH (NOLOCK)
                        WHERE YEAR(FECHA) > 2023
                          AND ACTIVO = 0
                          AND motivo IN ('REPROCESO', 'REPOSICION')
                          AND LTRIM(RTRIM(correlvouc)) IN ({b_placeholders})
                          AND LTRIM(RTRIM(numot)) IN ({r_placeholders})
                        ORDER BY correlvouc, numot, FECHA DESC
                        """,
                        *batch_chunk, *route_chunk,
                    )
                    for correlvouc, numot, motivo1, area1, fecha, kneto in cursor.fetchall():
                        key = (_safe_str(correlvouc).strip(), _safe_str(numot).strip())
                        if key in wanted and key not in out:  # first row per pair = newest
                            out[key] = {
                                'motivo1': _safe_str(motivo1),
                                'area1': _safe_str(area1),
                                'report_date': fecha or False,
                                'to_reprocess': _safe_float(kneto),
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

        Line = self.env['control.pedido.line']
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
            }
            existing_lines.write(write_vals)
            updated += len(existing_lines)
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
