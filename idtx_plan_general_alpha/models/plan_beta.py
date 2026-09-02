
import logging
import pyodbc
from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

_SITPRO_DSN = (
    "DSN=ENBTEX1_DSN;PORT=1433;UID=sistemas;"
    "PWD=idtE#21@IRdc95;TDS_Version=7.3;Database=SITPRO;"
)

_SORTABLE = {
    'nro', 'fecha', 'numordped', 'occ', 'grem', 'vend1', 'razsoc', 'descrip',
    'descol', 'cdgcol', 'orden', 'pescl', 'kilos', 'fecvouc', 'voucher',
    'repos', 'kneto', 'liqdes', 'dia', 'gvtas', 'cc', 'receta', 'testado',
    'ctrl', 'fecalm', 'talm', 'fecdesp', 'calidad', 'cdgclie', 'cdgart',
    'tiptej', 'correl', 'item', 'cdgven', 't', 'pcpi', 'activo', 'partida',
    'numot', 'tipoventa1', 'telefono', 'preuni', 'fing', 'moneda', 'expo',
    'incoterms', 'fechadespa', 'mercado', 'ktejido', 'fectenido', 'fecacabado',
    'fecinitej', 'fecfin', 'keyes', 'keyes1', 'partiorig', 'descri',
    'estampado1', 'maq', 'barcod', 'coddiseno', 'diseno', 'metrosf', 'ancho',
    'prio', 'fechaplan', 'densid', 'feccc', 'fecgvtas', 'fechamod', 'barcodreo',
    'barcodpar', 'procsigui', 'hdr', 'xtf', 'hilo1', 'hilo2', 'hilo3', 'hilo4',
    'hilo5', 'hilo6', 'hilo7', 'hilo8', 'hilo9', 'hilo10', 'hiloc1', 'hiloc2',
    'hiloc3', 'hiloc4', 'hiloc5', 'hiloc6', 'hiloc7', 'hiloc8', 'hiloc9',
    'hiloc10', 'codigohilo', 'galga', 'fecactualiza', 'maq_proce', 'lote',
    'fectemo', 'fecteni', 'fecaca', 'fecreceta', 'unid', 'tj', 'fecini',
    'fechadespacho', 'fechil', 'fectej', 'htf', 'ficha', 'fecoc', 'procod',
    'talm_b', 'kbruto',
}

_SQL_COUNT = "SELECT COUNT(*) FROM pla_general_planta"


def _build_sql(order_clause, from_row, to_row):
    return f"""
        SELECT * FROM (
            SELECT
                ROW_NUMBER() OVER (ORDER BY {order_clause}) AS id,
                ISNULL(CAST(nro      AS INT),   0) AS nro,
                ISNULL(CAST(talm     AS INT),   0) AS talm,
                ISNULL(CAST(item     AS INT),   0) AS item,
                ISNULL(CAST(talm_b   AS INT),   0) AS talm_b,
                ISNULL(CAST(dia      AS INT),   0) AS dia,
                ISNULL(CAST(pescl    AS FLOAT), 0) AS pescl,
                ISNULL(CAST(kilos    AS FLOAT), 0) AS kilos,
                ISNULL(CAST(kneto    AS FLOAT), 0) AS kneto,
                ISNULL(CAST(preuni   AS FLOAT), 0) AS preuni,
                ISNULL(CAST(ktejido  AS FLOAT), 0) AS ktejido,
                ISNULL(CAST(metrosf  AS FLOAT), 0) AS metrosf,
                ISNULL(CAST(ancho    AS FLOAT), 0) AS ancho,
                ISNULL(CAST(kbruto   AS FLOAT), 0) AS kbruto,
                ISNULL(CAST(densid   AS FLOAT), 0) AS densid,
                CONVERT(date, fecha)         AS fecha,
                CONVERT(date, fecvouc)       AS fecvouc,
                CONVERT(date, fecdesp)       AS fecdesp,
                CONVERT(date, fing)          AS fing,
                CONVERT(date, fechadespa)    AS fechadespa,
                CONVERT(date, fectenido)     AS fectenido,
                CONVERT(date, fecacabado)    AS fecacabado,
                CONVERT(date, fecinitej)     AS fecinitej,
                CONVERT(date, fecfin)        AS fecfin,
                CONVERT(date, fecini)        AS fecini,
                CONVERT(date, fechadespacho) AS fechadespacho,
                CONVERT(date, fechil)        AS fechil,
                CONVERT(date, fectej)        AS fectej,
                CONVERT(date, fecoc)         AS fecoc,
                fecactualiza,
                ISNULL(repos,      0) AS repos,
                ISNULL(liqdes,     0) AS liqdes,
                ISNULL(gvtas,      0) AS gvtas,
                ISNULL(cc,         0) AS cc,
                ISNULL(pcpi,       0) AS pcpi,
                ISNULL(activo,     0) AS activo,
                ISNULL(expo,       0) AS expo,
                ISNULL(keyes,      0) AS keyes,
                ISNULL(keyes1,     0) AS keyes1,
                ISNULL(estampado1, 0) AS estampado1,
                ISNULL(tj,         0) AS tj,
                RTRIM(ISNULL(numordped,  '')) AS numordped,
                RTRIM(ISNULL(occ,        '')) AS occ,
                RTRIM(ISNULL(grem,       '')) AS grem,
                RTRIM(ISNULL(vend1,      '')) AS vend1,
                RTRIM(ISNULL(razsoc,     '')) AS razsoc,
                RTRIM(ISNULL(descrip,    '')) AS descrip,
                RTRIM(ISNULL(descol,     '')) AS descol,
                RTRIM(ISNULL(cdgcol,     '')) AS cdgcol,
                RTRIM(ISNULL(orden,      '')) AS orden,
                RTRIM(ISNULL(voucher,    '')) AS voucher,
                RTRIM(ISNULL(receta,     '')) AS receta,
                RTRIM(ISNULL(testado,    '')) AS testado,
                RTRIM(ISNULL(ctrl,       '')) AS ctrl,
                RTRIM(ISNULL(fecalm,     '')) AS fecalm,
                RTRIM(ISNULL(calidad,    '')) AS calidad,
                RTRIM(ISNULL(cdgclie,    '')) AS cdgclie,
                RTRIM(ISNULL(cdgart,     '')) AS cdgart,
                RTRIM(ISNULL(tiptej,     '')) AS tiptej,
                RTRIM(ISNULL(correl,     '')) AS correl,
                RTRIM(ISNULL(cdgven,     '')) AS cdgven,
                RTRIM(ISNULL(t,          '')) AS t,
                RTRIM(ISNULL(partida,    '')) AS partida,
                RTRIM(ISNULL(numot,      '')) AS numot,
                RTRIM(ISNULL(tipoventa1, '')) AS tipoventa1,
                RTRIM(ISNULL(telefono,   '')) AS telefono,
                RTRIM(ISNULL(moneda,     '')) AS moneda,
                RTRIM(ISNULL(incoterms,  '')) AS incoterms,
                RTRIM(ISNULL(mercado,    '')) AS mercado,
                RTRIM(ISNULL(partiorig,  '')) AS partiorig,
                RTRIM(ISNULL(descri,     '')) AS descri,
                RTRIM(ISNULL(maq,        '')) AS maq,
                RTRIM(ISNULL(barcod,     '')) AS barcod,
                RTRIM(ISNULL(coddiseno,  '')) AS coddiseno,
                RTRIM(ISNULL(diseno,     '')) AS diseno,
                RTRIM(ISNULL(prio,       '')) AS prio,
                RTRIM(ISNULL(fechaplan,  '')) AS fechaplan,
                RTRIM(ISNULL(feccc,      '')) AS feccc,
                RTRIM(ISNULL(fecgvtas,   '')) AS fecgvtas,
                RTRIM(ISNULL(fechamod,   '')) AS fechamod,
                RTRIM(ISNULL(barcodreo,  '')) AS barcodreo,
                RTRIM(ISNULL(barcodpar,  '')) AS barcodpar,
                RTRIM(ISNULL(procsigui,  '')) AS procsigui,
                RTRIM(ISNULL(hdr,        '')) AS hdr,
                RTRIM(ISNULL(xtf,        '')) AS xtf,
                RTRIM(ISNULL(hilo1,      '')) AS hilo1,
                RTRIM(ISNULL(hilo2,      '')) AS hilo2,
                RTRIM(ISNULL(hilo3,      '')) AS hilo3,
                RTRIM(ISNULL(hilo4,      '')) AS hilo4,
                RTRIM(ISNULL(hilo5,      '')) AS hilo5,
                RTRIM(ISNULL(hilo6,      '')) AS hilo6,
                RTRIM(ISNULL(hilo7,      '')) AS hilo7,
                RTRIM(ISNULL(hilo8,      '')) AS hilo8,
                RTRIM(ISNULL(hilo9,      '')) AS hilo9,
                RTRIM(ISNULL(hilo10,     '')) AS hilo10,
                RTRIM(ISNULL(hiloc1,     '')) AS hiloc1,
                RTRIM(ISNULL(hiloc2,     '')) AS hiloc2,
                RTRIM(ISNULL(hiloc3,     '')) AS hiloc3,
                RTRIM(ISNULL(hiloc4,     '')) AS hiloc4,
                RTRIM(ISNULL(hiloc5,     '')) AS hiloc5,
                RTRIM(ISNULL(hiloc6,     '')) AS hiloc6,
                RTRIM(ISNULL(hiloc7,     '')) AS hiloc7,
                RTRIM(ISNULL(hiloc8,     '')) AS hiloc8,
                RTRIM(ISNULL(hiloc9,     '')) AS hiloc9,
                RTRIM(ISNULL(hiloc10,    '')) AS hiloc10,
                RTRIM(ISNULL(codigohilo, '')) AS codigohilo,
                RTRIM(ISNULL(galga,      '')) AS galga,
                RTRIM(ISNULL(maq_proce,  '')) AS maq_proce,
                RTRIM(ISNULL(lote,       '')) AS lote,
                RTRIM(ISNULL(fectemo,    '')) AS fectemo,
                RTRIM(ISNULL(fecteni,    '')) AS fecteni,
                RTRIM(ISNULL(fecaca,     '')) AS fecaca,
                RTRIM(ISNULL(fecreceta,  '')) AS fecreceta,
                RTRIM(ISNULL(unid,       '')) AS unid,
                RTRIM(ISNULL(htf,        '')) AS htf,
                RTRIM(ISNULL(ficha,      '')) AS ficha,
                RTRIM(ISNULL(procod,     '')) AS procod,
                ISNULL(CAST(observ  AS VARCHAR(MAX)), '') AS observ,
                ISNULL(CAST(rutafin AS VARCHAR(MAX)), '') AS rutafin
            FROM pla_general_planta
        ) AS paged
        WHERE id BETWEEN {from_row} AND {to_row}
    """


def _serialize(val):
    if val is None:
        return False
    if hasattr(val, 'isoformat'):
        return val.isoformat()
    return val


class PlanBeta(models.Model):
    _name = 'plan.beta'
    _description = 'Plan General Planta (SITPRO)'
    _auto = False
    _log_access = False

    def init(self):
        self.env.cr.execute(
            'CREATE OR REPLACE VIEW "%s" AS SELECT 1 AS id WHERE FALSE'
            % self._table
        )

    nro          = fields.Integer(string='Nro',          readonly=True)
    talm         = fields.Integer(string='T.Alm',        readonly=True)
    item         = fields.Integer(string='Item',          readonly=True)
    talm_b       = fields.Integer(string='T.Alm B',      readonly=True)
    dia          = fields.Integer(string='Días',          readonly=True)
    pescl        = fields.Float(string='Peso Cl.',        readonly=True, digits=(12, 3))
    kilos        = fields.Float(string='Kilos',           readonly=True, digits=(12, 3))
    kneto        = fields.Float(string='K.Neto',          readonly=True, digits=(12, 3))
    preuni       = fields.Float(string='P.Unitario',      readonly=True, digits=(12, 2))
    ktejido      = fields.Float(string='K.Tejido',        readonly=True, digits=(12, 3))
    metrosf      = fields.Float(string='Metros F.',       readonly=True, digits=(12, 3))
    ancho        = fields.Float(string='Ancho',           readonly=True, digits=(12, 3))
    kbruto       = fields.Float(string='K.Bruto',         readonly=True, digits=(12, 3))
    densid       = fields.Float(string='Densidad',        readonly=True, digits=(12, 3))
    fecha        = fields.Date(string='Fecha',            readonly=True)
    fecvouc      = fields.Date(string='F.Voucher',        readonly=True)
    fecdesp      = fields.Date(string='F.Despacho',       readonly=True)
    fing         = fields.Date(string='F.Ingreso',        readonly=True)
    fechadespa   = fields.Date(string='F.Despa.',         readonly=True)
    fectenido    = fields.Date(string='F.Tenido',         readonly=True)
    fecacabado   = fields.Date(string='F.Acabado',        readonly=True)
    fecinitej    = fields.Date(string='F.Ini.Tej.',       readonly=True)
    fecfin       = fields.Date(string='F.Fin',            readonly=True)
    fecini       = fields.Date(string='F.Inicio',         readonly=True)
    fechadespacho = fields.Date(string='F.Despazo',       readonly=True)
    fechil       = fields.Date(string='F.Hilo',           readonly=True)
    fectej       = fields.Date(string='F.Tejido',         readonly=True)
    fecoc        = fields.Date(string='F.OC',             readonly=True)
    fecactualiza = fields.Datetime(string='F.Actualiza',  readonly=True)
    repos        = fields.Boolean(string='Repos.',         readonly=True)
    liqdes       = fields.Boolean(string='Liq.Des.',       readonly=True)
    gvtas        = fields.Boolean(string='G.Vtas',         readonly=True)
    cc           = fields.Boolean(string='CC',             readonly=True)
    pcpi         = fields.Boolean(string='PCPI',           readonly=True)
    activo       = fields.Boolean(string='Activo',         readonly=True)
    expo         = fields.Boolean(string='Expo',           readonly=True)
    keyes        = fields.Boolean(string='Keyes',          readonly=True)
    keyes1       = fields.Boolean(string='Keyes1',         readonly=True)
    estampado1   = fields.Boolean(string='Estampado',      readonly=True)
    tj           = fields.Boolean(string='TJ',             readonly=True)
    observ       = fields.Text(string='Observ.',           readonly=True)
    rutafin      = fields.Text(string='Ruta Fin',          readonly=True)
    numordped    = fields.Char(string='Orden Pedido',      readonly=True)
    occ          = fields.Char(string='OCC',               readonly=True)
    grem         = fields.Char(string='Grem.',             readonly=True)
    vend1        = fields.Char(string='Vendedor',          readonly=True)
    razsoc       = fields.Char(string='Razón Social',      readonly=True)
    descrip      = fields.Char(string='Artículo',          readonly=True)
    descol       = fields.Char(string='Color',             readonly=True)
    cdgcol       = fields.Char(string='Cód.Color',         readonly=True)
    orden        = fields.Char(string='Orden',             readonly=True)
    voucher      = fields.Char(string='Voucher',           readonly=True)
    receta       = fields.Char(string='Receta',            readonly=True)
    testado      = fields.Char(string='Testado',           readonly=True)
    ctrl         = fields.Char(string='Ctrl',              readonly=True)
    fecalm       = fields.Char(string='F.Alm.Tex',         readonly=True)
    calidad      = fields.Char(string='Calidad',           readonly=True)
    cdgclie      = fields.Char(string='Cód.Cliente',       readonly=True)
    cdgart       = fields.Char(string='Cód.Art.',          readonly=True)
    tiptej       = fields.Char(string='Tip.Tej.',          readonly=True)
    correl       = fields.Char(string='Correlativo',       readonly=True)
    cdgven       = fields.Char(string='Cód.Vend.',         readonly=True)
    t            = fields.Char(string='T',                 readonly=True)
    partida      = fields.Char(string='Partida',           readonly=True)
    numot        = fields.Char(string='N.OT',              readonly=True)
    tipoventa1   = fields.Char(string='Tipo Venta',        readonly=True)
    telefono     = fields.Char(string='Teléfono',          readonly=True)
    moneda       = fields.Char(string='Moneda',            readonly=True)
    incoterms    = fields.Char(string='Incoterms',         readonly=True)
    mercado      = fields.Char(string='Mercado',           readonly=True)
    partiorig    = fields.Char(string='Part.Orig.',        readonly=True)
    descri       = fields.Char(string='Cond.Pago',         readonly=True)
    maq          = fields.Char(string='Máquina',           readonly=True)
    barcod       = fields.Char(string='Barcode',           readonly=True)
    coddiseno    = fields.Char(string='Cód.Diseño',        readonly=True)
    diseno       = fields.Char(string='Diseño',            readonly=True)
    prio         = fields.Char(string='Prioridad',         readonly=True)
    fechaplan    = fields.Char(string='F.Plan',            readonly=True)
    feccc        = fields.Char(string='F.CC',              readonly=True)
    fecgvtas     = fields.Char(string='F.G.Vtas',          readonly=True)
    fechamod     = fields.Char(string='F.Mod.',            readonly=True)
    barcodreo    = fields.Char(string='Barcode Reo.',      readonly=True)
    barcodpar    = fields.Char(string='Barcode Par.',      readonly=True)
    procsigui    = fields.Char(string='Proc.Sig.',         readonly=True)
    hdr          = fields.Char(string='HDR',               readonly=True)
    xtf          = fields.Char(string='XTF',               readonly=True)
    hilo1        = fields.Char(string='Hilo 1',            readonly=True)
    hilo2        = fields.Char(string='Hilo 2',            readonly=True)
    hilo3        = fields.Char(string='Hilo 3',            readonly=True)
    hilo4        = fields.Char(string='Hilo 4',            readonly=True)
    hilo5        = fields.Char(string='Hilo 5',            readonly=True)
    hilo6        = fields.Char(string='Hilo 6',            readonly=True)
    hilo7        = fields.Char(string='Hilo 7',            readonly=True)
    hilo8        = fields.Char(string='Hilo 8',            readonly=True)
    hilo9        = fields.Char(string='Hilo 9',            readonly=True)
    hilo10       = fields.Char(string='Hilo 10',           readonly=True)
    hiloc1       = fields.Char(string='Hilo C1',           readonly=True)
    hiloc2       = fields.Char(string='Hilo C2',           readonly=True)
    hiloc3       = fields.Char(string='Hilo C3',           readonly=True)
    hiloc4       = fields.Char(string='Hilo C4',           readonly=True)
    hiloc5       = fields.Char(string='Hilo C5',           readonly=True)
    hiloc6       = fields.Char(string='Hilo C6',           readonly=True)
    hiloc7       = fields.Char(string='Hilo C7',           readonly=True)
    hiloc8       = fields.Char(string='Hilo C8',           readonly=True)
    hiloc9       = fields.Char(string='Hilo C9',           readonly=True)
    hiloc10      = fields.Char(string='Hilo C10',          readonly=True)
    codigohilo   = fields.Char(string='Cód.Hilo',          readonly=True)
    galga        = fields.Char(string='Galga',             readonly=True)
    maq_proce    = fields.Char(string='Maq.Proc.',         readonly=True)
    lote         = fields.Char(string='Lote',              readonly=True)
    fectemo      = fields.Char(string='F.Termof.',         readonly=True)
    fecteni      = fields.Char(string='F.Tenido2',         readonly=True)
    fecaca       = fields.Char(string='F.Acab.2',          readonly=True)
    fecreceta    = fields.Char(string='F.Receta',          readonly=True)
    unid         = fields.Char(string='Unidad',            readonly=True)
    htf          = fields.Char(string='HTF',               readonly=True)
    ficha        = fields.Char(string='Ficha',             readonly=True)
    procod       = fields.Char(string='Proc.Cod.',         readonly=True)


    def _sitpro_connect(self):
        return pyodbc.connect(_SITPRO_DSN)

    def _parse_order(self, order):
        if not order:
            return 'nro ASC'
        parts = []
        for part in order.split(','):
            tokens = part.strip().split()
            if not tokens:
                continue
            col = tokens[0].lower()
            if col not in _SORTABLE:
                continue
            direction = 'DESC' if len(tokens) > 1 and tokens[1].upper() == 'DESC' else 'ASC'
            parts.append(f"{col} {direction}")
        return ', '.join(parts) if parts else 'nro ASC'

    def _fetch_rows(self, offset=0, limit=80, order=None):
        order_clause = self._parse_order(order)
        sql = _build_sql(order_clause, offset + 1, offset + limit)
        try:
            conn = self._sitpro_connect()
            cursor = conn.cursor()
            cursor.execute(sql)
            cols = [desc[0] for desc in cursor.description]
            rows = cursor.fetchall()
            conn.close()
        except Exception as exc:
            _logger.error("PlanBeta._fetch_rows: %s", exc)
            return []

        return [
            {col: _serialize(val) for col, val in zip(cols, row)}
            for row in rows
        ]

    def _count_rows(self):
        try:
            conn = self._sitpro_connect()
            cursor = conn.cursor()
            cursor.execute(_SQL_COUNT)
            count = cursor.fetchone()[0]
            conn.close()
            return int(count)
        except Exception as exc:
            _logger.error("PlanBeta._count_rows: %s", exc)
            return 0


    @api.model
    def web_search_read(self, domain, specification, offset=0, limit=None, order=None, count_limit=None):
        records = self._fetch_rows(offset=offset, limit=limit or 80, order=order)
        return {
            'length':  self._count_rows(),
            'records': records,
        }

    @api.model
    def search_count(self, domain, limit=None):
        return self._count_rows()

    @api.model
    def search_fetch(self, domain, field_names=None, offset=0, limit=None, order=None):
        count = self._count_rows()
        offset_val = offset or 0
        lim = limit if limit is not None else count
        start = offset_val + 1
        end = min(offset_val + lim, count)
        ids = list(range(start, end + 1)) if start <= end else []
        return self.browse(ids)

    def export_data(self, fields_to_export):
        if not (self.env.is_admin() or self.env.user.has_group('base.group_allow_export')):
            raise UserError("No tiene permisos para exportar datos.")

        total = self._count_rows()
        all_rows = self._fetch_rows(offset=0, limit=total, order='nro ASC')

        result_rows = []
        for row in all_rows:
            result_row = []
            for fname in fields_to_export:
                if fname in ('.id', 'id'):
                    result_row.append(str(row.get('id', '')))
                else:
                    val = row.get(fname, False)
                    result_row.append('' if (val is False or val is None) else val)
            result_rows.append(result_row)

        return {'datas': result_rows}
