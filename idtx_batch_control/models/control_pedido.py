# -*- coding: utf-8 -*-
import os
import datetime
import dbf
import pyodbc
pyodbc.setDecimalSeparator(".")
from odoo import models, fields, api, _
from odoo.exceptions import UserError

# ---------- Helpers DBF ----------
def _read_dbf(folder, filename, codepage="cp1252", limit=None):
    path = os.path.join(folder, filename)
    if not os.path.isfile(path):
        raise UserError(_("No existe el DBF: %s") % path)

    t = dbf.Table(path, codepage=codepage)
    t.open(mode=dbf.READ_ONLY)
    try:
        rows = []
        i = 0
        for rec in t:
            # Este filtro ya no es necesario
            # if 'FECOC' in t.field_names: 
            # Filtros de tablavta_cab_pedido
            if rec['FECOC'] is None or \
                not rec['FECOC'] or \
                rec['FECOC'] < datetime.date(2025,6,30) or \
                not rec['activo'] or \
                rec['tipoventa'][:10] != 'VENTA DE T':
                continue
            if limit and i >= limit:
                break
            rows.append({fn: rec[fn] for fn in t.field_names})
            i += 1
        return rows
    finally:
        t.close()

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


def _safe_date(v):
    if not v:
        return False
    if isinstance(v, datetime.datetime):
        return v.date()
    if isinstance(v, datetime.date):
        return v
    # si viene como string, intenta YYYY-MM-DD
    try:
        return datetime.date.fromisoformat(str(v)[:10])
    except Exception:
        return False


def _safe_bool(v):
    if v in (True, False):
        return bool(v)
    if v is None:
        return False
    s = str(v).strip().upper()
    return s in ("T", "Y", "1", "SI", "S", "TRUE")

FIRST_AREA = {
    'TINTORERIA',
}
SECOND_AREA = {
    'ACABADO',
}
THIRD_AREA = {
    'CALIDAD',
}

# ---------- Models ----------
class ControlPedido(models.Model):
    _name = "control.pedido"
    _description = "Control de Pedido"
    _order = "num_days desc, fecha desc, numordped desc"
    _rec_name = 'numordped'

    # ----- Campos DBF (TODOS) -----
    fecha = fields.Date(string="Order Date")
    fecoc = fields.Date(string="Customer Order Date")
    numordped = fields.Char(string="Order Number", required=True, index=True)
    tipoventa = fields.Char(string="Type of Sale")
    total_weight = fields.Float('Total Weight')
    line_ids = fields.One2many("control.pedido.line", "pedido_id", string="Detail")
    process = fields.Char('Process', compute='_compute_process', store=True)
    area = fields.Char('Area', compute='_compute_process', store=True)
    num_days = fields.Integer('Number of Days', compute='_compute_num_days', store=True)
    state = fields.Selection([
        ('on', 'On Time'),
        ('de', 'Delayed'),
        ('do', 'Done'),
    ], string='State', compute='_compute_state', default='on', store=True)

    _sql_constraints = [
        ("control_pedido_numordped_uniq", "unique(numordped)", "Ya existe un pedido con ese NUMORDPED."),
    ]

    @api.depends('fecoc')
    def _compute_num_days(self):
        for rec in self:
            rec.num_days = (fields.Date.context_today(self) - rec.fecoc).days if rec.fecoc else 0

    @api.depends('line_ids','num_days')
    def _compute_state(self):
        for rec in self:
            result = 'on'
            if rec.num_days:
                if not len(rec.line_ids) and rec.num_days > 12:
                    result = 'de'
                elif rec.num_days > 12 and rec.num_days <= 20:
                    if any(l.area in FIRST_AREA for l in rec.line_ids) or rec.area == 'TEJEDURIA':
                        result = 'de'
                elif rec.num_days > 20 and rec.num_days <= 25:
                    if any(l.area in SECOND_AREA for l in rec.line_ids) or rec.area == 'TEJEDURIA':
                        result = 'de'
                elif rec.num_days > 25 and rec.num_days <= 30:
                    if any(l.area in THIRD_AREA for l in rec.line_ids) or rec.area == 'TEJEDURIA':
                        result = 'de'
                elif rec.num_days > 30:
                    result = 'de'
            rec.state = result
    
    @api.depends('line_ids')
    def _compute_process(self):
        for rec in self:
            suma = sum(rec.line_ids.mapped('kilograms'))
            if rec.line_ids and suma >= rec.total_weight:
                for hr in rec.line_ids:
                    if hr.area in FIRST_AREA:
                        break
                    elif hr.area in SECOND_AREA:
                        break
                    elif hr.area in THIRD_AREA:
                        break
                rec.process = hr.process or 'FASE NO RECONOCIDA'
                rec.area = hr.area or 'AREA NO CONOCIDA'
            else:
                rec.process = 'TEJIDO'
                rec.area = 'TEJEDURIA'

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
            # _logger.error(f"Error conectando a SQL Server: {e}")
            raise UserError(f"No se pudo conectar a SQL Server: {e}")
        
    # ----- Sync -----
    @api.model
    def sync_from_dbf(self, folder, codepage="cp1252", limit_cab=5000, limit_det=5000):
        cab = _read_dbf(folder, "vta_cab_pedido.dbf", codepage=codepage, limit=limit_cab)

        # 1) Lista de nums válidos
        nums = []
        cab_by_num = {}
        for r in cab:
            num = _safe_str(r.get("NUMORDPED"))
            if not num:
                continue
            nums.append(num)
            cab_by_num[num] = r

        if not nums:
            return {"created": 0, "updated": 0}

        # 2) Traer pedidos existentes de una sola vez
        existing = self.search([("numordped", "in", nums)])
        existing_map = {p.numordped: p for p in existing}

        created = 0
        updated = 0

        # 3) Crear/actualizar cabeceras con menos llamadas ORM
        #    (si quieres aún más rápido, se puede hacer SQL directo, pero mejor mantener ORM)
        pedidos = self.browse()
        for num in nums:
            r = cab_by_num[num]
            vals = {
                'fecha': _safe_date(r.get('FECHA')),
                'fecoc': _safe_date(r.get('FECOC')),
                'numordped': num,
                'tipoventa': _safe_str(r.get('TIPOVENTA')),
                'total_weight': _safe_float(r.get('TOTKIL')),
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
                    WITH KilosPorBarCod AS (
                        SELECT 
                            B.BarCod,
                            SUM(D.DisPieKil) AS TotalKilos
                        FROM BARCAD B
                        JOIN DISALD D 
                            ON B.DisCod = D.DisCod
                        GROUP BY B.BarCod
                    ),
                    UltimoProcesoTerminado AS (
                        SELECT 
                            BarCod, 
                            MAX(BarOrdLin) AS BarOrdLin_Terminado
                        FROM BARFAS
                        WHERE BarCodReo = 0
                        AND BarFasDTI <> '1753-01-01'
                        AND BarFasDTF <> '1753-01-01'
                        GROUP BY BarCod
                    )
                    SELECT
                        bc.BarItem2 AS Pedido,
                        bf_next.BarCod AS HojaDeRuta,
                        kp.TotalKilos AS PesoTotal,
                        fp.FasDsc AS Proceso_Siguiente,
                        sp.area AS Area
                    FROM BARCAD bc
                    JOIN KilosPorBarCod kp
                        ON kp.BarCod = bc.BarCod
                    JOIN UltimoProcesoTerminado upt
                        ON upt.BarCod = bc.BarCod

                    CROSS APPLY (
                        SELECT TOP (1)
                            bf2.BarCod,
                            bf2.FasCod,
                            bf2.BarFasDTI,
                            bf2.BarFasDTF,
                            bf2.BarOrdLin
                        FROM BARFAS bf2
                        WHERE bf2.BarCod = bc.BarCod
                        AND bf2.BarCodReo = 0
                        AND bf2.BarOrdLin > upt.BarOrdLin_Terminado
                        ORDER BY bf2.BarOrdLin
                    ) bf_next
                    JOIN FASPRO fp
                        ON fp.FasCod = bf_next.FasCod
                    LEFT JOIN estatus_reproceso sp
                        ON fp.FasCod = sp.fase
                    WHERE bc.BarCodReo = 0
                    AND bc.BarItem2 IN ({placeholders});
            """

            cursor.execute(query, nums)

            cols = [c[0] for c in cursor.description]
            # rows = [dict(zip(cols, row)) for row in cursor.fetchall()]
            rows = []
            try:
                for row in cursor.fetchall():
                    # fuerza a tupla por si pyodbc.Row raro
                    row_t = tuple(row)
                    rows.append({cols[i]: row_t[i] for i in range(len(cols))})
            except Exception as e:
                # imprime info útil para ubicar el detonante
                print("ERROR al leer rows desde SQL Server:", repr(e))
                print("Columnas:", cols)
                # intenta leer una fila para ver tipos
                try:
                    one = cursor.fetchone()
                    print("Una fila (fetchone):", one)
                    if one:
                        print("Tipos:", [type(x) for x in one])
                except Exception as e2:
                    print("También falló fetchone:", repr(e2))
                raise

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
        vals_to_print = set()
        for dr in rows:
            num = _safe_str(dr.get("Pedido"))
            pedido = existing_map.get(num)
            if not pedido:
                continue

            vals_line = self.env["control.pedido.line"]._vals_from_det_row(dr)
            vals_to_print.add(vals_line['process'])
            line_cmds_by_pedido.setdefault(pedido.id, []).append((0, 0, vals_line))

        # Write por pedido que tenga líneas (normalmente mucho menos que N)
        for pid, cmds in line_cmds_by_pedido.items():
            self.browse(pid).write({"line_ids": cmds})
        print(vals_to_print)
        return {"created": created, "updated": updated}


    def action_sync_from_dbf(self):
        folder = '/mnt/fox/sit06/dbf'
        # folder = self.env["ir.config_parameter"].sudo().get_param("foxpro.folder")
        if not folder:
            raise UserError(_("Configura 'control.folder' con la ruta montada (ej: /mnt/fox/sit06/dbf)."))
        res = self.sync_from_dbf(folder)
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

    pedido_id = fields.Many2one("control.pedido", required=True, ondelete="cascade")
    route = fields.Char(string="Route")
    process = fields.Char(string="Next Process")
    area = fields.Char('Area')
    kilograms = fields.Float('Kilograms')

    @api.model
    def _vals_from_det_row(self, dr):
        # get = dr.cursor_description
        return {
            "route": _safe_str(dr["HojaDeRuta"]),
            "kilograms": _safe_float(dr["PesoTotal"]),
            "process": _safe_str(dr["Proceso_Siguiente"]),
            "area": _safe_str(dr["Area"]),
        }
