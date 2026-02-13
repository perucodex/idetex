# -*- coding: utf-8 -*-
import datetime
import pytz
import dbf
import pyodbc
pyodbc.setDecimalSeparator(".")
from odoo import models, fields, api, _
from odoo.exceptions import UserError

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
        out = {}  # {numordped: suma_kneto}
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
        # Filtros de tabla vta_cab_pedido
        if rec['FECOC'] is None or \
            not _safe_date(rec['FECOC']) or \
            rec['FECOC'] < datetime.date(2025,6,30) or \
            not _safe_bool(rec['activo']) or \
            _safe_str(rec['tipoventa'][:10]) != 'VENTA DE T':# or \
            # 'MUESTRA' in _safe_str(rec['RAZSOC'])or \
            # 'IDEAS' in _safe_str(rec['RAZSOC'])or \
            # 'IDETEX' in _safe_str(rec['RAZSOC']):
            return True
    else:
        # Filtros de tabla tej_produccion
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

def _safe_str(v):
    if v is None:
        return False
    if isinstance(v, (datetime.date, datetime.datetime)):
        return v.isoformat()
    try:
        return str(v).strip()
    except Exception:
        return False


def _safe_float(v):
    if v is None or v is False:
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(str(v).strip())
    except Exception:
        return 0.0


def _safe_date(v, user_tz=None):
    if not v:
        return False

    user_tz = user_tz or pytz.UTC

    # --- Normaliza a datetime ---
    if isinstance(v, datetime.datetime):
        dt = v
    elif isinstance(v, datetime.date):
        # si solo viene fecha, pon hora 00:00
        dt = datetime.datetime.combine(v, datetime.time.min)
    else:
        # intenta parsear 'YYYY-MM-DD' o 'YYYY-MM-DD HH:MM:SS'
        s = str(v).strip()
        try:
            dt = datetime.datetime.fromisoformat(s[:19])
        except Exception:
            try:
                d = datetime.date.fromisoformat(s[:10])
                dt = datetime.datetime.combine(d, datetime.time.min)
            except Exception:
                return False

    # --- Asume que dt está en TZ del usuario si viene naive ---
    if dt.tzinfo is None:
        dt = user_tz.localize(dt)

    # --- Convierte a UTC y devuelve NAIVE (lo que Odoo exige) ---
    dt_utc = dt.astimezone(pytz.UTC).replace(tzinfo=None)
    return dt_utc

def _safe_bool(v):
    if v in (True, False):
        return bool(v)
    if v is None:
        return False
    s = str(v).strip().upper()
    return s in ("T", "Y", "1", "SI", "S", "TRUE")

FIRST_AREA = {
    'PRE TINTORERIA',
    'TEJEDURIA',
}
SECOND_AREA = {
    'TINTORERIA',
    'PRE ESTAMPADO',
}
THIRD_AREA = {
    'ESTAMPADO',
    'PRE ACABADO',
}
FOURTH_AREA = {
    'ACABADO',
    'CONTROL DE CALIDAD',
}

# ---------- Models ----------
class ControlPedido(models.Model):
    _name = "control.pedido"
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = "Control de Pedido"
    _order = "num_days desc, state desc, fecoc desc, numordped desc"
    _rec_name = 'numordped'

    # ----- Campos DBF (TODOS) -----
    fecha = fields.Date(string="Order Date")
    fecoc = fields.Date(string="Customer Order Date")
    numordped = fields.Char(string="Order Number", required=True, index=True)
    customer = fields.Char('Customer')
    salesman = fields.Char('Salesman')
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

    # _sql_constraints = [
    #     ("control_pedido_numordped_uniq", "unique(numordped)", "Ya existe un pedido con ese Número de Orden."),
    # ]

    _product_code_unique = models.Constraint(
        'unique(numordped)',
        "Ya existe un pedido con ese Número de Orden!",
    )

    @api.depends('fecoc')
    def _compute_num_days(self):
        # for rec in self:
        #     rec.num_days = (fields.Date.context_today(self) - rec.fecoc).days if rec.fecoc else 0

        #### Misma funcion pero sin Domingos

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

            # Busca por prioridad, no por orden de las líneas
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

    # Liquidar y revertir orden
    def settle_order(self):
        res = _settle_order_dbf("/mnt/fox/sit06/dbf/vta_cab_pedido.dbf", self.numordped, not self.is_active)
        if res:
            self.is_active = not self.is_active
        return res

    # -----------------------------------------
    # 🔌 CONEXION SQL SERVER
    # -----------------------------------------
    def _get_sql_connection(self):
        try:
            conn = pyodbc.connect(
                "DSN=ENBTEX1_DSN;"
                "PORT=1433;"
                "UID=sistemas;"
                "PWD=idtE#21@IRdc95;"
                "TDS_Version=7.3;"
            )
            return conn
        except Exception as e:
            raise UserError(f"No se pudo conectar a SQL Server: {e}")
        
    # ----- Sync -----
    @api.model
    def sync_from_dbf(self):
        # cab = _read_dbf("/mnt/fox/sit06/dbf/vta_cab_pedido.dbf")

        # # 1) Lista de nums válidos
        # nums = []
        # cab_by_num = {}
        # for r in cab:
        #     num = _safe_str(r.get("NUMORDPED"))
        #     if not num:
        #         continue
        #     nums.append(num)
        #     cab_by_num[num] = r
        cab_by_num = {}
        nums = []
        nums_to_settle = []
        for rec in _iter_dbf("/mnt/fox/sit06/dbf/vta_cab_pedido.dbf"):
            # filtros cab: evita _safe_date 2 veces si FECOC ya es date
            fecoc = rec["FECOC"]
            if not fecoc or fecoc < datetime.date(2025, 6, 30):
                continue
            if not _safe_bool(rec["ACTIVO"]):
                num = _safe_str(rec["NUMORDPED"])
                nums_to_settle.append(num)    
                continue
            if _safe_str(rec["TIPOVENTA"][:10]) != "VENTA DE T":
                continue
            num = _safe_str(rec["NUMORDPED"])
            if not num:
                continue
            nums.append(num)
            cab_by_num[num] = {
                "fecha": _safe_date(rec["FECHA"]),
                "fecoc": _safe_date(rec["FECOC"]),
                "customer": _safe_str(rec["RAZSOC"]),
                "salesman": _safe_str(rec["USUARIO"]),
                "tipoventa": _safe_str(rec["TIPOVENTA"]),
                "total_weight": _safe_float(rec["TOTKIL"]),
                "is_active": _safe_bool(rec["ACTIVO"]),
            }

        if not nums:
            return {"created": 0, "updated": 0}

        self.search([("numordped", "in", nums_to_settle)]).is_active = False

        # --- Producción (tej_produccion) -> sumar KNETO por pedido ---
        nums_set = set(nums)
        produced_by_num = _sum_kneto_by_pedido("/mnt/fox/sit06/dbf/tej_produccion.dbf", nums_set)

        # produced_by_num = {}   # { '000123': 1500.25, ... }
        # for pr in prod:
        #     pnum = _safe_str(pr.get("NUMORDPED"))
        #     kneto = _safe_float(pr.get("KNETO"))
        #     produced_by_num[pnum] = produced_by_num.get(pnum, 0.0) + kneto

        # 2) Traer pedidos existentes de una sola vez
        existing = self.search([("numordped", "in", nums)])
        existing_map = {p.numordped: p for p in existing}

        created = 0
        updated = 0

        # 3) Crear/actualizar cabeceras con menos llamadas ORM
        #    (si quieres aún más rápido, se puede hacer SQL directo, pero mejor mantener ORM)
        pedidos = self.browse()
        for num in nums:
            rec = cab_by_num[num]
            base = cab_by_num[num]
            vals = {
                **base,
                'numordped': num,
                'produced_weight': produced_by_num.get(num, 0.0),
            }

            pedido = existing_map.get(num)
            if pedido:
                pedido.write(vals)
                updated += 1
            else:
                pedido = self.create(vals)
                created += 1
                existing_map[num] = pedido

            pedidos |= pedido

        # 4) BORRADO MASIVO de líneas (una sola vez)
        if pedidos:
            self.env["control.pedido.line"].search([("pedido_id", "in", pedidos.ids)]).unlink()

        # 5) UNA sola conexión y UNA sola consulta MSSQL para todos los pedidos
        conn = self._get_sql_connection()
        try:
            cursor = conn.cursor()

            placeholders = ",".join(["?"] * len(nums))

            query = f"""
            WITH PedidoHDR AS (
                SELECT
                    bc.BarCod,
                    bc.BarCodReo,
                    bc.BarCodPar,
                    bc.BarItem2 AS Pedido,
                    bc.BarItem4 AS Partida,
                    bc.BarColNom as ColorCode,
                    bc.BarNomCli as ColorName
                FROM BARCAD bc
                WHERE bc.BarItem2 IN ({placeholders})
                -- si quieres SOLO rutas "principales" como muchas pantallas:
                -- AND ISNULL(bc.BarCodPar,'') = ''
            ),
            Kilos AS (
                SELECT
                    bp.BarCod,
                    bp.BarCodReo,
                    SUM(bp.BarPieKil) AS Kilos
                FROM BARPIE bp
                WHERE bp.BarCod IN (SELECT BarCod FROM PedidoHDR)
                GROUP BY bp.BarCod, bp.BarCodReo
            )
            SELECT
                h.Pedido,
                h.Partida,
                h.BarCod AS HojaDeRuta,
                h.BarCodReo,
                h.BarCodPar,
                h.ColorCode,
                h.ColorName,
                ISNULL(k.Kilos, 0) AS PesoTotal,
                fp.FasDsc AS Proceso_Ultimo,
                sp.area AS Area,
                bf_last.BarFasDTI AS FechaInicio,
                bf_last.BarFasDTF AS FechaFinal
            FROM PedidoHDR h
            JOIN Kilos k
            ON k.BarCod = h.BarCod
            AND k.BarCodReo = h.BarCodReo
            AND k.Kilos > 0
            OUTER APPLY (
                SELECT TOP (1)
                    bf.FasCod,
                    bf.BarFasDTI,
                    bf.BarFasDTF,
                    bf.BarOrdLin
                FROM BARFAS bf
                WHERE bf.BarCod = h.BarCod
                AND bf.BarCodReo = h.BarCodReo
                AND ISNULL(bf.BarCodPar,'') = ISNULL(h.BarCodPar,'')   -- 🔑 IMPORTANTÍSIMO
                AND bf.BarFasDTI > '1753-01-01'
                AND bf.BarFasDTF > '1753-01-01'
                ORDER BY bf.BarOrdLin DESC, bf.BarFasDTF DESC, bf.BarFasDTI DESC
            ) bf_last

            LEFT JOIN FASPRO fp
            ON fp.FasCod = bf_last.FasCod
            LEFT JOIN estatus_reproceso sp
            ON sp.fase = bf_last.FasCod

            ORDER BY h.Pedido, h.BarCod, h.BarCodReo, h.BarCodPar;
            """
            print(nums)
            cursor.execute(query, *nums)

            cols = [c[0] for c in cursor.description]
            rows = [dict(zip(cols, row)) for row in cursor.fetchall()]

            # --- 5.1) Traer detalle de procesos (BARFAS) para las hojas de ruta encontradas ---
            barcods = set()
            for r in rows:
                bc = _safe_str(r.get("HojaDeRuta"))
                if bc:
                    barcods.add(bc)

            processes_by_valid_key = {}
            if barcods:
                # Ojo con el límite de parámetros en SQL Server (2100). Si son muchos, lotear.
                # Por ahora asumimos que no excede (nums de pedidos -> barcods razonables)
                # Si barcods es muy grande, hacer chunks.
                unique_barcods = list(barcods)
                
                # Chunking simple por si acaso (ej. 1000 en 1000)
                chunk_size = 1000
                for i in range(0, len(unique_barcods), chunk_size):
                    chunk = unique_barcods[i:i + chunk_size]
                    placeholders_bc = ",".join(["?"] * len(chunk))
                    
                    q_procs = f"""
                        SELECT 
                            bf.BarCod, bf.BarOrdLin, bf.FasCod, bf.MaqCodBis, bf.BarFasDTI, bf.BarFasDTF,
                            bf.BarCodReo, bf.BarCodPar,
                            fp.FasDsc
                        FROM BARFAS bf
                        LEFT JOIN FASPRO fp ON fp.FasCod = bf.FasCod
                        WHERE bf.BarCod IN ({placeholders_bc})
                        ORDER BY bf.BarCod, bf.BarOrdLin
                    """
                    cursor.execute(q_procs, *chunk)
                    p_cols = [c[0] for c in cursor.description]
                    p_rows = [dict(zip(p_cols, row)) for row in cursor.fetchall()]

                    for pr in p_rows:
                        bc = _safe_str(pr.get("BarCod"))
                        # Clave compuesta: (BarCod, BarCodReo, BarCodPar)
                        # Ojo: BarCodPar puede ser NULL o vacío en BD, normalizar a '' para coincidir
                        bcreo = _safe_str(pr.get("BarCodReo")) or ''
                        bcpar = _safe_str(pr.get("BarCodPar")) or ''
                        
                        key = (bc, bcreo, bcpar)

                        # Map FasDsc to fasCod field for display
                        desc = _safe_str(pr.get("FasDsc")) or _safe_str(pr.get("FasCod"))
                        
                        # Mapeo a campos de control.proceso.lines
                        vals_proc = {
                            "barcod": bc,
                            "barOrdLin": int(pr.get("BarOrdLin") or 0),
                            "fasCod": desc,
                            "maqCodBis": _safe_str(pr.get("MaqCodBis")),
                            # Fechas: cuidado con formats. _safe_date maneja selects de pyodbc (datetime)
                            "barFasDTI": pr.get("BarFasDTI"), 
                            "barFasDTF": pr.get("BarFasDTF"),
                        }
                        processes_by_valid_key.setdefault(key, []).append((0, 0, vals_proc))

        finally:
            try:
                cursor.close()
            except Exception:
                pass
            try:
                conn.close()
            except Exception:
                pass

        # 6) Insertar líneas en batch por pedido (sin write repetitivo)
        line_cmds_by_pedido = {}
        for dr in rows:
            num = _safe_str(dr.get("Pedido"))
            pedido = existing_map.get(num)
            if not pedido:
                continue

            vals_line = self.env["control.pedido.line"]._vals_from_det_row(dr)
            
            # Inyectar procesos si existen (Match por clave compuesta)
            bc = _safe_str(dr.get("HojaDeRuta"))
            bcreo = _safe_str(dr.get("BarCodReo")) or ''
            bcpar = _safe_str(dr.get("BarCodPar")) or ''

            key = (bc, bcreo, bcpar)
            
            if key in processes_by_valid_key:
                vals_line["proceso_ids"] = processes_by_valid_key[key]

            line_cmds_by_pedido.setdefault(pedido.id, []).append((0, 0, vals_line))

        # Write por pedido que tenga líneas (normalmente mucho menos que N)
        for pid, cmds in line_cmds_by_pedido.items():
            self.browse(pid).write({"line_ids": cmds})
        return {"created": created, "updated": updated}


    def action_sync_from_dbf(self):
        res = self.sync_from_dbf()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "FoxPro → Odoo",
                "message": f"Creados: {res['created']} | Actualizados: {res['updated']}",
                "sticky": False,
            }
        }


class ControlPedidoLine(models.Model):
    _name = "control.pedido.line"
    _description = "Control Pedido (Detalle)"
    _rec_name = 'batch'

    pedido_id = fields.Many2one("control.pedido", required=True, ondelete="cascade")
    route = fields.Char(string="Route")
    barcodreo = fields.Char('Reprocess')
    batch = fields.Char('Batch')
    process = fields.Char(string="Next Process")
    area = fields.Char('Area')
    kilograms = fields.Float('Kilograms')
    start_date = fields.Datetime('Start Date')
    end_date = fields.Datetime('End Date')
    colorcode = fields.Char('Color Code')
    colorname = fields.Char('Color Name')

    proceso_ids = fields.One2many(
        "control.proceso.lines",
        "pedido_line_id",
        string="Procesos"
    )

    @api.model
    def _vals_from_det_row(self, dr):
        user_tz = pytz.timezone(self.env.user.tz or 'UTC')
        return {
            "route": _safe_str(dr["HojaDeRuta"]),
            "barcodreo": _safe_str(dr["BarCodReo"]),
            "batch": _safe_str(dr["Partida"]),
            "kilograms": _safe_float(dr["PesoTotal"]),
            "process": _safe_str(dr["Proceso_Ultimo"]) or 'SIN AVANCE',
            "area": _safe_str(dr["Area"]) or 'VOUCHER',
            "start_date": _safe_date(dr["FechaInicio"], user_tz),
            "end_date": _safe_date(dr["FechaFinal"], user_tz),
            "colorcode": _safe_str(dr["ColorCode"]),
            "colorname": _safe_str(dr["ColorName"]),
        }

    def action_start_process(self):
        for rec in self:
            rec.start_date = fields.Datetime.now()

    def action_end_process(self):
        for rec in self:
            rec.end_date = fields.Datetime.now()


# =====================================================
# MODELO PROCESOS
# =====================================================

class ControlProcesoLine(models.Model):
    _name = "control.proceso.lines"
    _description = "Procesos BARFAS"
    _order = "barOrdLin asc"

    pedido_line_id = fields.Many2one(
        "control.pedido.line",
        required=True,
        ondelete="cascade"
    )

    barcod = fields.Char("Hoja de Ruta")
    barOrdLin = fields.Integer("Orden")
    fasCod = fields.Char("Proceso")
    maqCodBis = fields.Char("Máquina")

    barFasDTI = fields.Datetime("Fecha Inicio")
    barFasDTF = fields.Datetime("Fecha Fin")

    # =====================================

    def action_start(self):
        for rec in self:

            if rec.barFasDTI:
                raise UserError("Este proceso ya fue iniciado.")

            prev = self.search([
                ("pedido_line_id", "=", rec.pedido_line_id.id),
                ("barOrdLin", "<", rec.barOrdLin),
                ("barFasDTF", "=", False)
            ])

            if prev:
                raise UserError("Debe finalizar el proceso anterior primero.")

            now = fields.Datetime.now()

            rec._update_sql("BarFasDTI", now)
            rec.barFasDTI = now

    # =====================================

    def action_finish(self):
        for rec in self:

            if not rec.barFasDTI:
                raise UserError("Debe iniciar el proceso primero.")

            if rec.barFasDTF:
                raise UserError("Este proceso ya fue finalizado.")

            now = fields.Datetime.now()

            rec._update_sql("BarFasDTF", now)
            rec.barFasDTF = now

    # =====================================

    def _update_sql(self, field_name, value):
        conn = self.pedido_line_id.pedido_id._get_sql_connection()
        cursor = conn.cursor()

        query = f"""
            UPDATE BARFAS
            SET {field_name} = ?
            WHERE BarCod = ?
              AND BarOrdLin = ?
        """

        cursor.execute(query, value, self.barcod, self.barOrdLin)
        conn.commit()

        cursor.close()
        conn.close()