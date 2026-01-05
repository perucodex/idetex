# # -*- coding: utf-8 -*-
# import os
# import dbf

# from odoo import models, fields, api, _
# from odoo.exceptions import UserError


# def _read_dbf(folder, filename, codepage="cp1252", limit=None, cabeceras=False):
#     path = os.path.join(folder, filename)
#     if not os.path.isfile(path):
#         raise UserError(_("No existe el archivo DBF: %s") % path)

#     t = dbf.Table(path, codepage=codepage)
#     t.open(mode=dbf.READ_ONLY)
#     try:
#         out = []
#         i = 0
#         for rec in t:
#             if 'FECHA' in t.field_names:
#                 a = rec['FECHA'].year
#                 if a != 2025:
#                     continue
#             if cabeceras:
#                 a = rec['NUMORDPED'].strip()
#                 if a not in cabeceras:
#                     continue
#             if limit and i >= limit:
#                 break
#             out.append({fn: rec[fn] for fn in t.field_names})
#             i += 1
#         return out
#     finally:
#         t.close()


# class FoxproPedido(models.Model):
#     _name = "foxpro.pedido"
#     _description = "Pedido FoxPro (Cabecera)"
#     _order = "fecha desc, numordped desc"

#     numordped = fields.Char(string="N° Orden Pedido", required=True, index=True)
#     fecha = fields.Date(string="Fecha")
#     tipoventa = fields.Char(string="Tipo Venta")
#     cdgclie = fields.Char(string="Cliente (Código)")
#     razsoc = fields.Char(string="Razón Social")
#     moneda = fields.Char(string="Moneda")

#     subtotal = fields.Float(string="Subtotal")
#     canigv = fields.Float(string="IGV")
#     totnet = fields.Float(string="Total")

#     observ = fields.Char(string="Observación")
#     activo = fields.Boolean(string="Activo")
#     cancelado = fields.Boolean(string="Cancelado")

#     line_ids = fields.One2many("foxpro.pedido.line", "pedido_id", string="Detalle")

#     _sql_constraints = [
#         ("foxpro_pedido_numordped_uniq", "unique(numordped)", "Ya existe un pedido con ese NUMORDPED."),
#     ]

#     @api.model
#     def sync_from_dbf(self, folder, limit_cab=500, limit_det=5000):
#         cab = _read_dbf(folder, "vta_cab_pedido.dbf", limit=limit_cab)
#         cabeceras = []
#         for r in cab:
#             num = str(r.get("NUMORDPED") or "").strip()
#             cabeceras.append(num)
#         det = _read_dbf(folder, "vta_det_pedido.dbf", limit=limit_det, cabeceras=cabeceras)

#         # Indexa detalle por NUMORDPED
#         det_by_num = {}
#         for r in det:
#             k = str(r.get("NUMORDPED") or "").strip()
#             if not k:
#                 continue
#             det_by_num.setdefault(k, []).append(r)

#         created = 0
#         updated = 0

#         for r in cab:
#             num = str(r.get("NUMORDPED") or "").strip()
#             if not num:
#                 continue

#             vals = {
#                 "numordped": r.get("NUMORDPED"),
#                 "fecha": r.get("FECHA"),
#                 "tipoventa": r.get("TIPOVENTA"),
#                 "cdgclie": r.get("CDGCLIE"),
#                 "razsoc": r.get("RAZSOC"),
#                 "moneda": r.get("MONEDA"),
#                 "subtotal": float(r.get("SUBTOTAL") or 0.0),
#                 "canigv": float(r.get("CANIGV") or 0.0),
#                 "totnet": float(r.get("TOTNET") or 0.0),
#                 "observ": r.get("OBSERV"),
#                 "activo": bool(r.get("ACTIVO")) if r.get("ACTIVO") is not None else False,
#                 "cancelado": bool(r.get("CANCELADO")) if r.get("CANCELADO") is not None else False,
#             }

#             pedido = self.search([("numordped", "=", num)], limit=1)
#             if pedido:
#                 pedido.write(vals)
#                 updated += 1
#             else:
#                 pedido = self.create(vals)
#                 created += 1

#             # Estrategia simple: refrescar detalle (borrar y recrear)
#             pedido.line_ids.unlink()

#             lines_cmds = []
#             for dr in det_by_num.get(num, []):
#                 lines_cmds.append((0, 0, {
#                     "item": str(dr.get("ITEM") or "").strip(),
#                     "cdgart": dr.get("CDGART"),
#                     "cdgcol": dr.get("CDGCOL"),
#                     "descol": dr.get("DESCOL"),
#                     "kilo": float(dr.get("KILO") or 0.0),
#                     "metros": float(dr.get("METROS") or 0.0),
#                     "preuni": float(dr.get("PREUNI") or 0.0),
#                     "importe": float(dr.get("IMPORTE") or 0.0),
#                     "descrip": dr.get("DESCRIP"),
#                     "obsart": dr.get("OBSART"),
#                     "cancelado": bool(dr.get("CANCELADO")) if dr.get("CANCELADO") is not None else False,
#                 }))

#             if lines_cmds:
#                 pedido.write({"line_ids": lines_cmds})

#         return {"created": created, "updated": updated}

#     def action_sync_from_dbf(self):
#         folder = '/mnt/fox/sit06/JP_DBF'
#         if not folder:
#             raise UserError(_("Configura primero el parámetro del sistema 'foxpro.folder' (ruta montada)."))

#         res = self.sync_from_dbf(folder)
#         return {
#             "type": "ir.actions.client",
#             "tag": "display_notification",
#             "params": {
#                 "title": "FoxPro → Odoo",
#                 "message": f"Creados: {res['created']} | Actualizados: {res['updated']}",
#                 "sticky": False,
#             }
#         }


# class FoxproPedidoLine(models.Model):
#     _name = "foxpro.pedido.line"
#     _description = "Pedido FoxPro (Detalle)"
#     _order = "item asc, id asc"

#     pedido_id = fields.Many2one("foxpro.pedido", required=True, ondelete="cascade")
#     item = fields.Char(string="Item")
#     cdgart = fields.Char(string="Artículo")
#     cdgcol = fields.Char(string="Color")
#     descol = fields.Char(string="Desc. Color")
#     descrip = fields.Char(string="Descripción")

#     kilo = fields.Float(string="Kilos")
#     metros = fields.Float(string="Metros")
#     preuni = fields.Float(string="Precio Unit.")
#     importe = fields.Float(string="Importe")

#     obsart = fields.Char(string="Obs. Artículo")
#     cancelado = fields.Boolean(string="Cancelado")


# -*- coding: utf-8 -*-
import os
import datetime
import dbf

from odoo import models, fields, api, _
from odoo.exceptions import UserError


# ---------- Helpers DBF ----------
def _read_dbf(folder, filename, codepage="cp1252", limit=None, cabeceras=False):
    path = os.path.join(folder, filename)
    if not os.path.isfile(path):
        raise UserError(_("No existe el DBF: %s") % path)

    t = dbf.Table(path, codepage=codepage)
    t.open(mode=dbf.READ_ONLY)
    try:
        rows = []
        i = 0
        for rec in t:
            if 'FECHA' in t.field_names:
                a = rec['FECHA'].year
                b = rec['FECHA'].month
                if a != 2025 or a == 2025 and b < 10:
                    continue
            if cabeceras:
                a = rec['NUMORDPED'].strip()
                if a not in cabeceras:
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


# ---------- Field maps ----------
# DBF -> Odoo field (solo cambia donde no es válido el nombre)
DET_FIELD_MAP = {
    "FECTEÑ": "fecten",
}
CAB_FIELD_MAP = {}  # todos válidos tal cual (lowercase)


# ---------- Models ----------
class FoxproPedido(models.Model):
    _name = "foxpro.pedido"
    _description = "FoxPro Pedido (Cabecera)"
    _order = "fecha desc, numordped desc"

    # ----- Campos DBF (TODOS) -----
    fecha = fields.Date(string="FECHA")
    numordped = fields.Char(string="NUMORDPED", required=True, index=True)
    orden = fields.Char(string="ORDEN")
    t = fields.Char(string="T")
    tipoventa = fields.Char(string="TIPOVENTA")
    cdgclie = fields.Char(string="CDGCLIE")
    cdgtipmer = fields.Char(string="CDGTIPMER")
    cdgtipven = fields.Char(string="CDGTIPVEN")
    lab = fields.Char(string="LAB")
    condpago = fields.Char(string="CONDPAGO")
    cdgven = fields.Char(string="CDGVEN")
    telefono = fields.Char(string="TELEFONO")
    grem = fields.Char(string="GREM")
    occ = fields.Char(string="OCC")
    tj = fields.Char(string="TJ")
    tn = fields.Char(string="TN")
    metros = fields.Float(string="METROS")
    metrosf = fields.Float(string="METROSF")
    totkil = fields.Float(string="TOTKIL")
    subtotal = fields.Float(string="SUBTOTAL")
    canigv = fields.Float(string="CANIGV")
    totnet = fields.Float(string="TOTNET")
    observ = fields.Text(string="OBSERV")
    useranul = fields.Char(string="USERANUL")
    obsanul = fields.Text(string="OBSANUL")
    fecanul = fields.Date(string="FECANUL")
    ctrl = fields.Char(string="CTRL")
    gvtas = fields.Char(string="GVTAS")
    fecgvtas = fields.Date(string="FECGVTAS")
    cc = fields.Char(string="CC")
    feccc = fields.Date(string="FECCC")
    pcpi = fields.Char(string="PCPI")
    fecpcpi = fields.Date(string="FECPCPI")
    procesa = fields.Boolean(string="PROCESA")
    activo = fields.Boolean(string="ACTIVO")
    dstock = fields.Boolean(string="DSTOCK")
    almacen = fields.Char(string="ALMACEN")
    tej = fields.Char(string="TEJ")
    ten = fields.Char(string="TEN")
    cancelado = fields.Boolean(string="CANCELADO")
    docliq = fields.Char(string="DOCLIQ")
    tipocondpa = fields.Char(string="TIPOCONDPA")
    editada = fields.Boolean(string="EDITADA")
    usuario = fields.Char(string="USUARIO")
    feccrea = fields.Datetime(string="FECCREA")
    maquina = fields.Char(string="MAQUINA")
    alming = fields.Char(string="ALMING")
    almegr = fields.Char(string="ALMEGR")
    tipdesp = fields.Char(string="TIPDESP")
    razsoc = fields.Char(string="RAZSOC")
    moneda = fields.Char(string="MONEDA")
    htf = fields.Char(string="HTF")
    xtf = fields.Char(string="XTF")
    scaneo = fields.Boolean(string="SCANEO")
    dirdespcl = fields.Char(string="DIRDESPCL")
    disdespcl = fields.Char(string="DISDESPCL")
    provdespcl = fields.Char(string="PROVDESPCL")
    dptodespcl = fields.Char(string="DPTODESPCL")
    rendim = fields.Float(string="RENDIM")
    encog = fields.Float(string="ENCOG")
    datacol = fields.Char(string="DATACOL")
    revirado = fields.Char(string="REVIRADO")
    solidez = fields.Char(string="SOLIDEZ")
    idtipo = fields.Char(string="IDTIPO")
    planh = fields.Char(string="PLANH")
    plant = fields.Char(string="PLANT")
    plann = fields.Char(string="PLANN")
    fechaplan = fields.Date(string="FECHAPLAN")
    um = fields.Char(string="UM")
    um1 = fields.Char(string="UM1")
    fechadespa = fields.Date(string="FECHADESPA")
    incoterms = fields.Char(string="INCOTERMS")
    expo = fields.Boolean(string="EXPO")
    dato1 = fields.Char(string="DATO1")
    fechagio = fields.Date(string="FECHAGIO")
    numreq = fields.Char(string="NUMREQ")
    procesado = fields.Boolean(string="PROCESADO")
    oprela = fields.Char(string="OPRELA")
    fecinipedi = fields.Date(string="FECINIPEDI")
    feccrea1 = fields.Datetime(string="FECCREA1")
    fecoc = fields.Date(string="FECOC")
    empresa = fields.Char(string="EMPRESA")

    # ----- Relación detalle -----
    line_ids = fields.One2many("foxpro.pedido.line", "pedido_id", string="Detalle")

    _sql_constraints = [
        ("foxpro_pedido_numordped_uniq", "unique(numordped)", "Ya existe un pedido con ese NUMORDPED."),
    ]

    # ----- Sync -----
    @api.model
    def sync_from_dbf(self, folder, codepage="cp1252", limit_cab=500, limit_det=5000):
        cab = _read_dbf(folder, "vta_cab_pedido.dbf", codepage=codepage, limit=limit_cab)
        cabeceras = []
        for r in cab:
            num = str(r.get("NUMORDPED") or "").strip()
            cabeceras.append(num)
        det = _read_dbf(folder, "vta_det_pedido.dbf", codepage=codepage, limit=limit_det, cabeceras=cabeceras)

        # index detalle por NUMORDPED
        det_by = {}
        for r in det:
            k = _safe_str(r.get("NUMORDPED"))
            if not k:
                continue
            det_by.setdefault(k, []).append(r)

        created = 0
        updated = 0

        for r in cab:
            num = _safe_str(r.get("NUMORDPED"))
            if not num:
                continue

            vals = {
                # Fechas / datetimes
                "fecha": _safe_date(r.get("FECHA")),
                "fecanul": _safe_date(r.get("FECANUL")),
                "fecgvtas": _safe_date(r.get("FECGVTAS")),
                "feccc": _safe_date(r.get("FECCC")),
                "fecpcpi": _safe_date(r.get("FECPCPI")),
                "fechaplan": _safe_date(r.get("FECHAPLAN")),
                "fechadespa": _safe_date(r.get("FECHADESPA")),
                "fechagio": _safe_date(r.get("FECHAGIO")),
                "fecinipedi": _safe_date(r.get("FECINIPEDI")),
                "fecoc": _safe_date(r.get("FECOC")),
                "feccrea": r.get("FECCREA") if isinstance(r.get("FECCREA"), datetime.datetime) else False,
                "feccrea1": r.get("FECCREA1") if isinstance(r.get("FECCREA1"), datetime.datetime) else False,

                # Numericos
                "metros": _safe_float(r.get("METROS")),
                "metrosf": _safe_float(r.get("METROSF")),
                "totkil": _safe_float(r.get("TOTKIL")),
                "subtotal": _safe_float(r.get("SUBTOTAL")),
                "canigv": _safe_float(r.get("CANIGV")),
                "totnet": _safe_float(r.get("TOTNET")),
                "rendim": _safe_float(r.get("RENDIM")),
                "encog": _safe_float(r.get("ENCOG")),

                # Booleanos
                "procesa": _safe_bool(r.get("PROCESA")),
                "activo": _safe_bool(r.get("ACTIVO")),
                "dstock": _safe_bool(r.get("DSTOCK")),
                "cancelado": _safe_bool(r.get("CANCELADO")),
                "editada": _safe_bool(r.get("EDITADA")),
                "scaneo": _safe_bool(r.get("SCANEO")),
                "expo": _safe_bool(r.get("EXPO")),
                "procesado": _safe_bool(r.get("PROCESADO")),

                # Strings / texto
                "numordped": num,
                "orden": _safe_str(r.get("ORDEN")),
                "t": _safe_str(r.get("T")),
                "tipoventa": _safe_str(r.get("TIPOVENTA")),
                "cdgclie": _safe_str(r.get("CDGCLIE")),
                "cdgtipmer": _safe_str(r.get("CDGTIPMER")),
                "cdgtipven": _safe_str(r.get("CDGTIPVEN")),
                "lab": _safe_str(r.get("LAB")),
                "condpago": _safe_str(r.get("CONDPAGO")),
                "cdgven": _safe_str(r.get("CDGVEN")),
                "telefono": _safe_str(r.get("TELEFONO")),
                "grem": _safe_str(r.get("GREM")),
                "occ": _safe_str(r.get("OCC")),
                "tj": _safe_str(r.get("TJ")),
                "tn": _safe_str(r.get("TN")),
                "observ": r.get("OBSERV") or False,
                "useranul": _safe_str(r.get("USERANUL")),
                "obsanul": r.get("OBSANUL") or False,
                "ctrl": _safe_str(r.get("CTRL")),
                "gvtas": _safe_str(r.get("GVTAS")),
                "cc": _safe_str(r.get("CC")),
                "pcpi": _safe_str(r.get("PCPI")),
                "almacen": _safe_str(r.get("ALMACEN")),
                "tej": _safe_str(r.get("TEJ")),
                "ten": _safe_str(r.get("TEN")),
                "docliq": _safe_str(r.get("DOCLIQ")),
                "tipocondpa": _safe_str(r.get("TIPOCONDPA")),
                "usuario": _safe_str(r.get("USUARIO")),
                "maquina": _safe_str(r.get("MAQUINA")),
                "alming": _safe_str(r.get("ALMING")),
                "almegr": _safe_str(r.get("ALMEGR")),
                "tipdesp": _safe_str(r.get("TIPDESP")),
                "razsoc": _safe_str(r.get("RAZSOC")),
                "moneda": _safe_str(r.get("MONEDA")),
                "htf": _safe_str(r.get("HTF")),
                "xtf": _safe_str(r.get("XTF")),
                "dirdespcl": _safe_str(r.get("DIRDESPCL")),
                "disdespcl": _safe_str(r.get("DISDESPCL")),
                "provdespcl": _safe_str(r.get("PROVDESPCL")),
                "dptodespcl": _safe_str(r.get("DPTODESPCL")),
                "datacol": _safe_str(r.get("DATACOL")),
                "revirado": _safe_str(r.get("REVIRADO")),
                "solidez": _safe_str(r.get("SOLIDEZ")),
                "idtipo": _safe_str(r.get("IDTIPO")),
                "planh": _safe_str(r.get("PLANH")),
                "plant": _safe_str(r.get("PLANT")),
                "plann": _safe_str(r.get("PLANN")),
                "um": _safe_str(r.get("UM")),
                "um1": _safe_str(r.get("UM1")),
                "incoterms": _safe_str(r.get("INCOTERMS")),
                "dato1": _safe_str(r.get("DATO1")),
                "numreq": _safe_str(r.get("NUMREQ")),
                "oprela": _safe_str(r.get("OPRELA")),
                "empresa": _safe_str(r.get("EMPRESA")),
            }

            pedido = self.search([("numordped", "=", num)], limit=1)
            if pedido:
                pedido.write(vals)
                updated += 1
            else:
                pedido = self.create(vals)
                created += 1

            # refrescar detalle
            pedido.line_ids.unlink()

            cmds = []
            for dr in det_by.get(num, []):
                cmds.append((0, 0, self.env["foxpro.pedido.line"]._vals_from_det_row(dr)))
            if cmds:
                pedido.write({"line_ids": cmds})

        return {"created": created, "updated": updated}

    def action_sync_from_dbf(self):
        folder = '/mnt/fox/sit06/JP_DBF'
        # folder = self.env["ir.config_parameter"].sudo().get_param("foxpro.folder")
        if not folder:
            raise UserError(_("Configura 'foxpro.folder' con la ruta montada (ej: /mnt/fox/sit06/JP_DBF)."))
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


class FoxproPedidoLine(models.Model):
    _name = "foxpro.pedido.line"
    _description = "FoxPro Pedido (Detalle)"
    _order = "item asc, id asc"

    pedido_id = fields.Many2one("foxpro.pedido", required=True, ondelete="cascade")

    # ----- Campos DBF detalle (TODOS) -----
    numordped = fields.Char(string="NUMORDPED", index=True)
    item = fields.Char(string="ITEM")
    cdgart = fields.Char(string="CDGART")
    cdgcol = fields.Char(string="CDGCOL")
    descol = fields.Char(string="DESCOL")
    dato = fields.Char(string="DATO")
    gal = fields.Char(string="GAL")
    ancho = fields.Float(string="ANCHO")
    ancmin = fields.Float(string="ANCMIN")
    ancmax = fields.Float(string="ANCMAX")
    densidad = fields.Float(string="DENSIDAD")
    denmax = fields.Float(string="DENMAX")
    denmin = fields.Float(string="DENMIN")
    rend = fields.Float(string="REND")
    rendmax = fields.Float(string="RENDMAX")
    rendmin = fields.Float(string="RENDMIN")
    tiptej = fields.Char(string="TIPTEJ")
    luz = fields.Char(string="LUZ")
    lavado = fields.Char(string="LAVADO")
    frote = fields.Char(string="FROTE")
    luzsudor = fields.Char(string="LUZSUDOR")
    acabado = fields.Char(string="ACABADO")
    encogim_a = fields.Char(string="ENCOGIM_A")
    encogim_l = fields.Char(string="ENCOGIM_L")
    revirado = fields.Char(string="REVIRADO")
    luces = fields.Char(string="LUCES")
    antipiling = fields.Char(string="ANTIPILING")
    blanqueado = fields.Char(string="BLANQUEADO")
    rama1 = fields.Char(string="RAMA1")
    secado = fields.Char(string="SECADO")
    compactado = fields.Char(string="COMPACTADO")
    perchado = fields.Char(string="PERCHADO")
    rama2 = fields.Char(string="RAMA2")
    esmerilado = fields.Char(string="ESMERILADO")
    tamble = fields.Char(string="TAMBLE")
    abridora = fields.Char(string="ABRIDORA")
    hidro = fields.Char(string="HIDRO")
    centrifuga = fields.Char(string="CENTRIFUGA")
    termofijad = fields.Char(string="TERMOFIJAD")
    lavado1 = fields.Char(string="LAVADO1")
    tiedye = fields.Char(string="TIEDYE")
    debore = fields.Char(string="DEBORE")
    plisado = fields.Char(string="PLISADO")
    tundido = fields.Char(string="TUNDIDO")
    estampado = fields.Char(string="ESTAMPADO")
    oxidado = fields.Char(string="OXIDADO")
    kilo = fields.Float(string="KILO")
    metros = fields.Float(string="METROS")
    pescl = fields.Float(string="PESCL")
    preuni = fields.Float(string="PREUNI")
    importe = fields.Float(string="IMPORTE")
    numot = fields.Char(string="NUMOT")
    lote = fields.Char(string="LOTE")
    kstock = fields.Boolean(string="KSTOCK")
    listado = fields.Char(string="LISTADO")
    opcol = fields.Char(string="OPCOL")
    act2 = fields.Char(string="ACT2")
    cancelado = fields.Boolean(string="CANCELADO")
    docliq = fields.Char(string="DOCLIQ")
    obsart = fields.Text(string="OBSART")
    tipoconpag = fields.Char(string="TIPOCONPAG")
    unid = fields.Char(string="UNID")
    tallas = fields.Char(string="TALLAS")
    correl = fields.Char(string="CORREL")
    voucher = fields.Char(string="VOUCHER")
    prerep = fields.Char(string="PREREP")
    descrip = fields.Char(string="DESCRIP")
    moneda = fields.Char(string="MONEDA")
    htf = fields.Char(string="HTF")
    xtf = fields.Char(string="XTF")
    comple = fields.Char(string="COMPLE")
    tend = fields.Char(string="TEND")
    fechaplan = fields.Date(string="FECHAPLAN")
    pobservaci = fields.Text(string="POBSERVACI")
    cmod = fields.Char(string="CMOD")
    fechamod = fields.Date(string="FECHAMOD")
    fechafin = fields.Date(string="FECHAFIN")
    diastrans = fields.Char(string="DIASTRANS")
    observacio = fields.Text(string="OBSERVACIO")
    diseno = fields.Char(string="DISENO")
    ncol = fields.Char(string="NCOL")
    metrosf = fields.Float(string="METROSF")
    procod = fields.Char(string="PROCOD")
    ruta = fields.Char(string="RUTA")
    materia = fields.Char(string="MATERIA")
    fechil = fields.Date(string="FECHIL")
    fectej = fields.Date(string="FECTEJ")
    fecarma = fields.Date(string="FECARMA")
    fecten = fields.Date(string="FECTEÑ")  # <- mapeado
    fecaca = fields.Date(string="FECACA")
    fecfin = fields.Date(string="FECFIN")
    mod = fields.Char(string="MOD")
    coddiseno = fields.Char(string="CODDISENO")
    lpar0 = fields.Char(string="LPAR0")
    htf1 = fields.Char(string="HTF1")
    lpar1 = fields.Char(string="LPAR1")
    htf2 = fields.Char(string="HTF2")
    lpar2 = fields.Char(string="LPAR2")

    @api.model
    def _vals_from_det_row(self, dr):
        # Copia todos los campos (DBF -> Odoo) con conversion segura
        # Campo con Ñ: FECTEÑ -> fecten
        get = dr.get

        return {
            "numordped": _safe_str(get("NUMORDPED")),
            "item": _safe_str(get("ITEM")),
            "cdgart": _safe_str(get("CDGART")),
            "cdgcol": _safe_str(get("CDGCOL")),
            "descol": _safe_str(get("DESCOL")),
            "dato": _safe_str(get("DATO")),
            "gal": _safe_str(get("GAL")),
            "ancho": _safe_float(get("ANCHO")),
            "ancmin": _safe_float(get("ANCMIN")),
            "ancmax": _safe_float(get("ANCMAX")),
            "densidad": _safe_float(get("DENSIDAD")),
            "denmax": _safe_float(get("DENMAX")),
            "denmin": _safe_float(get("DENMIN")),
            "rend": _safe_float(get("REND")),
            "rendmax": _safe_float(get("RENDMAX")),
            "rendmin": _safe_float(get("RENDMIN")),
            "tiptej": _safe_str(get("TIPTEJ")),
            "luz": _safe_str(get("LUZ")),
            "lavado": _safe_str(get("LAVADO")),
            "frote": _safe_str(get("FROTE")),
            "luzsudor": _safe_str(get("LUZSUDOR")),
            "acabado": _safe_str(get("ACABADO")),
            "encogim_a": _safe_str(get("ENCOGIM_A")),
            "encogim_l": _safe_str(get("ENCOGIM_L")),
            "revirado": _safe_str(get("REVIRADO")),
            "luces": _safe_str(get("LUCES")),
            "antipiling": _safe_str(get("ANTIPILING")),
            "blanqueado": _safe_str(get("BLANQUEADO")),
            "rama1": _safe_str(get("RAMA1")),
            "secado": _safe_str(get("SECADO")),
            "compactado": _safe_str(get("COMPACTADO")),
            "perchado": _safe_str(get("PERCHADO")),
            "rama2": _safe_str(get("RAMA2")),
            "esmerilado": _safe_str(get("ESMERILADO")),
            "tamble": _safe_str(get("TAMBLE")),
            "abridora": _safe_str(get("ABRIDORA")),
            "hidro": _safe_str(get("HIDRO")),
            "centrifuga": _safe_str(get("CENTRIFUGA")),
            "termofijad": _safe_str(get("TERMOFIJAD")),
            "lavado1": _safe_str(get("LAVADO1")),
            "tiedye": _safe_str(get("TIEDYE")),
            "debore": _safe_str(get("DEBORE")),
            "plisado": _safe_str(get("PLISADO")),
            "tundido": _safe_str(get("TUNDIDO")),
            "estampado": _safe_str(get("ESTAMPADO")),
            "oxidado": _safe_str(get("OXIDADO")),
            "kilo": _safe_float(get("KILO")),
            "metros": _safe_float(get("METROS")),
            "pescl": _safe_float(get("PESCL")),
            "preuni": _safe_float(get("PREUNI")),
            "importe": _safe_float(get("IMPORTE")),
            "numot": _safe_str(get("NUMOT")),
            "lote": _safe_str(get("LOTE")),
            "kstock": _safe_bool(get("KSTOCK")),
            "listado": _safe_str(get("LISTADO")),
            "opcol": _safe_str(get("OPCOL")),
            "act2": _safe_str(get("ACT2")),
            "cancelado": _safe_bool(get("CANCELADO")),
            "docliq": _safe_str(get("DOCLIQ")),
            "obsart": get("OBSART") or False,
            "tipoconpag": _safe_str(get("TIPOCONPAG")),
            "unid": _safe_str(get("UNID")),
            "tallas": _safe_str(get("TALLAS")),
            "correl": _safe_str(get("CORREL")),
            "voucher": _safe_str(get("VOUCHER")),
            "prerep": _safe_str(get("PREREP")),
            "descrip": _safe_str(get("DESCRIP")),
            "moneda": _safe_str(get("MONEDA")),
            "htf": _safe_str(get("HTF")),
            "xtf": _safe_str(get("XTF")),
            "comple": _safe_str(get("COMPLE")),
            "tend": _safe_str(get("TEND")),
            "fechaplan": _safe_date(get("FECHAPLAN")),
            "pobservaci": get("POBSERVACI") or False,
            "cmod": _safe_str(get("CMOD")),
            "fechamod": _safe_date(get("FECHAMOD")),
            "fechafin": _safe_date(get("FECHAFIN")),
            "diastrans": _safe_str(get("DIASTRANS")),
            "observacio": get("OBSERVACIO") or False,
            "diseno": _safe_str(get("DISENO")),
            "ncol": _safe_str(get("NCOL")),
            "metrosf": _safe_float(get("METROSF")),
            "procod": _safe_str(get("PROCOD")),
            "ruta": _safe_str(get("RUTA")),
            "materia": _safe_str(get("MATERIA")),
            "fechil": _safe_date(get("FECHIL")),
            "fectej": _safe_date(get("FECTEJ")),
            "fecarma": _safe_date(get("FECARMA")),
            "fecten": _safe_date(get("FECTEÑ")),  # <- Ñ
            "fecaca": _safe_date(get("FECACA")),
            "fecfin": _safe_date(get("FECFIN")),
            "mod": _safe_str(get("MOD")),
            "coddiseno": _safe_str(get("CODDISENO")),
            "lpar0": _safe_str(get("LPAR0")),
            "htf1": _safe_str(get("HTF1")),
            "lpar1": _safe_str(get("LPAR1")),
            "htf2": _safe_str(get("HTF2")),
            "lpar2": _safe_str(get("LPAR2")),
        }
