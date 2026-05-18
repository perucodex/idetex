# -*- coding: utf-8 -*-

import re
import unicodedata
from pathlib import Path

import dbf
import pyodbc

from odoo import _, fields, models, api
from odoo.exceptions import UserError

pyodbc.setDecimalSeparator('.')

PADR_FIELDS = {'FICHA', 'CDGCLIE', 'RUC'}
TEXPLUS_EMPRCOD = '001'
TEXPLUS_ROUTE_TABLES = ['PROCES', 'Rutas', 'Ruta_ENBT']

PROCESS_TABLES = [
    {'process': ['TEJIDO CRUDO', 'SERV. TEJIDO'], 'table': 'tinto_crudo.dbf'},
    {'process': ['THERMOFIJADO ENTEMA', 'THERMOFIJADO MERSAN'], 'table': 'tinto_termo_2.dbf'},
    {'process': ['THERMOFIJADO RAMA', 'THERMOFIJADO DISPERSANTE/HUM', 'THERMO-BLANQUEO ACABADO', 'THERMO ACABADO'], 'table': 'tinto_abi_ter.dbf'},
    {'process': ['SECADO', 'SECADO RECETA 155', 'SECADO PP ESTAMPAR', 'SECADO LUBRICANTE COSTURA', 'SECADO SOLO AGUA', 'SECADO PP ESMERILAR', 'SECADO PP PERCHAR', 'SECADO INCLINACION FULL', 'SECADO RECETA 211', 'SECADO PP TEÑIR', 'SECADO ENGOMADO C/ORILLOS'], 'table': 'tinto_abi_sil.dbf'},
    {'process': ['ACABADO', 'ACAB RESINA LIBRE FORMALEHID', 'ACABADO RESINADO', 'PRESECADO 100% RESINADO 158', 'ACABADO RECETA 104', 'ACABADO RECETA 102', 'ACABADO RECETA 157', 'PRESECADO 100% RESINADO 71', 'ACABADO RECETA 156', 'PRESECADO 100% ACABADO 157', 'ACABADO WICKING', 'ACABADO LUBRICANTE COSTURA', 'ACABADO HIDROFILO TACTO SUAV', 'ACABADO LUXURY', 'ACABADO BESOCOOL', 'ACABADO RESINADO LUXURY', 'ACABADO CON CORTE DE ORILLOS', 'PRESECADO 50% SOLO AGUA', 'PRESECADO 100% ACABADO', 'PRESECADO100% ACA157 ENG/C O', 'ACABADO RESINADO 1/2 RECETA', 'ACABADO RESI LUXU RECETA 158', 'ACABADO RESINADO LANDS END', 'PRESECADO 100% ACABADO 104', 'ACABADO RESINADO C/ORILLOS', 'ACABADO ENGOMADO C/ORILLOS', 'RAMA ENGOMADO/CORTE ORILLOS', 'RAMA CON HUMECTANTE', 'SUAVIZADO PP PERCHAR', 'ACABADO RECETA 101', 'ACABADO RESINADO LACOSTE', 'ACABADO WICKING RECETA 76', 'ACABADO RECETA 120', 'ACABADO PIQUE TACTO LACOSTE', 'ACAB RESIN LUXURY 1/2 RECETA', 'ACABADO RECETA 209', 'ACABADO ENGOMADO', 'ACABADO SOLO AGUA SIN C/ORIL', 'ACABADO HIDROFILO', 'LAVADO Y ACABADO ROTOCLEAN', 'ACABADO RESI LUXURY POLYCRYL', 'ACABADO PP SUBLIMAR', 'ACABADO WICKING+ANTIMICROBIA'], 'table': 'tinto_abi_rama.dbf'},
    {'process': ['PERCHADORA', 'PERCHADO X REVEZ', 'PERCHADO 2 PASES'], 'table': 'tinto_abi_percha.dbf'},
    {'process': ['TUNDIDO SOLO PUNTAS', 'TUNDIDO'], 'table': 'tinto_abi_tundi.dbf'},
    {'process': ['ESMERILADO', 'ESMERILADO X CARA ESTAMPADA', 'ESMERILADO X CARA'], 'table': 'tinto_abi_esme.dbf'},
    {'process': ['TAMBLEADO'], 'table': 'tinto_abi_tam.dbf'},
    {'process': ['ABIERTO TINTO', 'ABRIDORA CON DUCHA 2 PASES'], 'table': 'tinto_abi_abri.dbf'},
    {'process': ['HIDROEXTRACTORA', 'HIDRO SUAVIZADO', 'HIDRO SUAVIZADO PIMA', 'HIDRO HUMECTADO', 'HIDRO SOLO AGUA MINIMA PRESI', 'HIDRO RESINADO', 'HIDRO SOLO SUAVIZANT COSTURA', 'HIDRO SUAVIZANTE PERCHADO', 'HIDRO SUAVIZADO LUXURY', 'HIDRO RESINADO LANDS SEND', 'HIDRO HIDROFILO TACTO SUAVE', 'HIDRO SUA HIDROFIL TACTO SUA', 'HIDRO EXPRIMIDO'], 'table': 'tinto_tub_hidro.dbf'},
    {'process': ['SECADO', 'SECADO TUBULAR'], 'table': 'tinto_tub_seca.dbf'},
    {'process': ['COMPACTADO', 'SANFORIZADO'], 'table': 'tinto_tub_compa.dbf'},
    {'process': ['CONTROL DE CALIDAD'], 'table': 'tinto_calidad.dbf'},
]

FIELD_NAMES = {
    'txcampo': 'T° por Campo',
    'velocidad': 'Velocidad',
    'turbulenci': 'Turbulencia',
    'anchomaq': 'Ancho de Entrada',
    'alimsuperi': 'Alimentador Superior',
    'aliminfe': 'Alimentador Inferior',
    'alimbrizq': 'Alimentador Brazo Izquierdo',
    'alimbrader': 'Alimentador Brazo Derecho',
    'inclitrama': 'Inclinación de Trama',
    'anchosale': 'Ancho de Salida',
    'densisale': 'Densidad de Salida',
    'presifoula': 'Presion de Foulard',
    'recetacaba': 'Receta de Acabado',
    'presion': 'Presión',
    'alimsale': 'Alimentador de Salida',
    'temperatura': 'Temperatura C°',
    'anchocadena': 'Ancho de Cadena',
    'anchocaden': 'Ancho de Cadena',
    'densidmaq': 'Densidad de Entrada',
    'maquina': 'Maquina',
    'regulpelo': 'Regulación de Pelo',
    'regulcpelo': 'Regulación de Contrapelo',
    'tensientra': 'Tensión de Entrada',
    'tensisale': 'Tensión de Salida',
    'npases': 'N° de Pases',
    'altercuchi': 'Alterno de Cuchilla',
    'tensisalid': 'Tensión de Salida',
    'rpm': 'RPM',
    'veltambor': 'Velocidad del Tambor',
    'presifaja': 'Presión de Faja',
    'presientra': 'Presión de Entrada',
    'aircalient': 'Aire Caliente',
    'airefrio': 'Aire Frío',
    'vapor': 'Vapor',
    'alimgarru': 'Alimentador de Garrucha',
    'alimfoular': 'Alimentador de Foulard',
    'presifoul2': 'Presion de Foulard 2',
    'aliment123': 'Alimentadores 1-2-3',
    'presifoul1': 'Presion de Foulard 1',
    'anchotela': 'Ancho de Entrada',
    'recetacab': 'Bastidor',
    'ventxcamp': 'Ventilación por Campo',
    'alimentra': 'Alimentador de Entrada',
    'anchoentra': 'Ancho de Entrada',
    'tempera1': 'Temperatura 1',
    'tempera2': 'Temperatura 2',
    'tempera3': 'Temperatura 3',
    'encogimiento': 'Encogimiento',
    'densidad': 'Densidad',
    'alimsupe': 'Alimentador Superior',
    'presifoular': 'Presion de Foulard',
    'pickup': '%% de Pick Up',
    'vibracion': 'Vibración',
    'sobrealim': 'Sobre Alimentación',
    'alimentaci': 'Alimentación',
    'temperatu': 'Temperatura',
    'velicidad': 'Velocidad',
    'vaporizado': 'Vaporizado',
    'densisalid': 'Ancho de Salida',
    'teflon': 'Teflon',
    'tension': 'Tensión',
    'humectado': 'Humectado',
    'ancho': 'Ancho',
    'encolargo': 'Encogimiento Largo',
    'encoancho': 'Encogimiento Ancho',
    'revirado': 'Revirado',
    'solidelava': 'Solidez de Lavado',
    'solidelava': 'Solidez al Lavado',
    'otros': 'Otros',
    'temperatur': 'Temperatura',
    'alimen': 'Alimentación',
    'densientra': 'Densidad de Entrada',
    'densisale': 'Densidad de Salida',
    'tensiing': 'Tensión de Entrada',
    'tensisal': 'Tensión de Salida',
    'obs': 'Observación',
}

PARAMETER_LABEL_ALIASES = {
    'ANCH DE ENTRADA': 'ANCHO DE ENTRADA',
    'TEMPERATURA C': 'TEMPERATURA',
}

def _clean_text(value):
    return (str(value or '')).strip()

def _normalize_label(value):
    text = _clean_text(value).upper()
    if not text:
        return ''
    text = ''.join(ch for ch in unicodedata.normalize('NFD', text) if unicodedata.category(ch) != 'Mn')
    text = re.sub(r'[^A-Z0-9]+', ' ', text)
    return re.sub(r'\s+', ' ', text).strip()

def _dbf_char(value, max_len=None):
    text = _clean_text(value)
    if max_len:
        text = text[:max_len]
    return text

def _dbf_padr(value, size):
    return _dbf_char(value, max_len=size).ljust(size)

def _dbf_number_text(value, digits=2):
    if value in (False, None, ''):
        return '0' if digits == 0 else '0.' + '0' * digits
    return f'{float(value):.{digits}f}'

def _phase_code(name):
    text = _clean_text(name).upper()
    if not text:
        return ''
    text = ''.join(ch for ch in unicodedata.normalize('NFD', text) if unicodedata.category(ch) != 'Mn')
    text = re.sub(r'[^A-Z0-9]+', '', text)
    return text[:12]

def _cab_width_value(value):
    number = float(value or 0.0)
    if not number:
        return 0.0
    # En FoxPro tinto_cab_ruta.ANCHO guarda 170 cm como 1.70.
    return round(number / 100.0, 2)

def _texplus_int(value):
    return int(round(float(value or 0.0))) if value not in (False, None, '') else 0

def _texplus_decimal(value):
    return float(value or 0.0)

def _normalize_export_prefix(value):
    prefix = _clean_text(value).upper()
    if prefix not in {'M', 'P', 'S'}:
        raise UserError(_('Debe ingresar un prefijo valido de una sola letra: M, P o S.'))
    return prefix

def _is_memo_field(field_type):
    if isinstance(field_type, str):
        return field_type.upper() == 'M'
    return field_type == ord('M')

class TechnicalSheet(models.Model):
    _inherit = 'technical.sheet'

    foxpro_article_prefix = fields.Char('FoxPro Article Prefix', size=1, copy=False)
    foxpro_article_code = fields.Char('FoxPro Article Code', compute='_compute_foxpro_article_code', store=True)
    foxpro_export_state = fields.Selection([
        ('draft', 'Not Exported'),
        ('done', 'Exported'),
        ('error', 'Export Error'),
    ], string='FoxPro Export State', default='draft', copy=False, readonly=True)
    foxpro_export_message = fields.Text('FoxPro Export Message', copy=False, readonly=True)
    foxpro_export_date = fields.Datetime('FoxPro Export Date', copy=False, readonly=True)
    fabric_composition_id = fields.Many2one(
        'texplus.tipart', string='Composicion',
        required=True,
        default=lambda self: self._default_fabric_composition_id(),
        help="Tipo de articulo del catalogo TIPART de TEXPLUS.")
    clipboard_summary = fields.Char(compute='_compute_clipboard_summary')

    @api.model
    def _default_fabric_composition_id(self):
        return self.env['texplus.tipart']._get_default_tipart().id

    @api.depends('product_code', 'foxpro_article_prefix')
    def _compute_foxpro_article_code(self):
        for sheet in self:
            if sheet.product_code and sheet.foxpro_article_prefix:
                sheet.foxpro_article_code = f"{sheet.foxpro_article_prefix}{sheet.product_code}"
            else:
                sheet.foxpro_article_code = ''

    @api.depends('foxpro_article_code', 'description', 'analysis_id.notes')
    def _compute_clipboard_summary(self):
        for sheet in self:
            sheet.clipboard_summary = "\n".join([
                sheet.foxpro_article_code or '',
                sheet.description or '',
                sheet.analysis_id.notes or '',
            ])

    def _get_texplus_articu_lookup_code(self):
        self.ensure_one()
        article_code = _clean_text(self.analysis_id.codpro)
        if article_code:
            return article_code[-15:]
        return _clean_text(self.product_code or self.analysis_id.product_code)

    @api.model
    def _get_texplus_articu_tipart_map(self, product_codes):
        codes = sorted({code for code in product_codes if code})
        if not codes:
            return {}

        conn = self._get_texplus_sql_connection()
        cursor = None
        rows = []
        try:
            cursor = conn.cursor()
            for start in range(0, len(codes), 800):
                chunk = codes[start:start + 800]
                placeholders = ",".join(["?"] * len(chunk))
                cursor.execute(
                    f"""
                    SELECT RIGHT(RTRIM(ArtCod), 15) AS code,
                           TipArtCod,
                           ArtFecCre
                      FROM ARTICU
                     WHERE EmprCod = ?
                       AND TipArtCod IS NOT NULL
                       AND RIGHT(RTRIM(ArtCod), 15) IN ({placeholders})
                    """,
                    TEXPLUS_EMPRCOD,
                    *chunk,
                )
                rows.extend(cursor.fetchall())
        finally:
            try:
                cursor.close()
            except Exception:
                pass
            conn.close()

        best_by_code = {}
        default_date = fields.Datetime.to_datetime('1900-01-01')
        for code, tipart_cod, date_value in rows:
            code = _clean_text(code)
            if not code or tipart_cod in (False, None, ''):
                continue
            date_value = fields.Datetime.to_datetime(date_value) if date_value else default_date
            current = best_by_code.get(code)
            if current is None or date_value > current[1]:
                best_by_code[code] = (int(tipart_cod), date_value)
        return {code: tipart_cod for code, (tipart_cod, _date_value) in best_by_code.items()}

    def _sync_fabric_compositions_from_texplus(self):
        Tipart = self.env['texplus.tipart']
        Tipart._sync_from_texplus()
        default_tipart = Tipart._get_default_tipart()

        sheets = (self or self.search([])).sudo()
        code_by_sheet = {
            sheet.id: sheet._get_texplus_articu_lookup_code()
            for sheet in sheets
        }
        tipart_by_code = self._get_texplus_articu_tipart_map(code_by_sheet.values())
        tipart_records_by_code = Tipart._ensure_tipart_codes(tipart_by_code.values())

        sheet_ids_by_tipart_id = {}
        matched = 0
        defaulted = 0
        for sheet in sheets:
            tipart_cod = tipart_by_code.get(code_by_sheet.get(sheet.id))
            tipart = tipart_records_by_code.get(tipart_cod) or default_tipart
            if tipart == default_tipart and not tipart_cod:
                defaulted += 1
            else:
                matched += 1
            if sheet.fabric_composition_id != tipart:
                sheet_ids_by_tipart_id.setdefault(tipart.id, []).append(sheet.id)

        for tipart_id, sheet_ids in sheet_ids_by_tipart_id.items():
            self.browse(sheet_ids).sudo().write({'fabric_composition_id': tipart_id})

        return {
            'total': len(sheets),
            'matched': matched,
            'defaulted': defaulted,
            'updated': sum(len(sheet_ids) for sheet_ids in sheet_ids_by_tipart_id.values()),
        }

    def action_sync_fabric_compositions_from_texplus(self):
        stats = self.search([])._sync_fabric_compositions_from_texplus()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('TEXPLUS'),
                'message': _(
                    'Composiciones actualizadas: %(updated)s de %(total)s fichas. '
                    'Coincidencias ARTICU: %(matched)s. Por defecto: %(defaulted)s.'
                ) % stats,
                'sticky': False,
                'type': 'success',
            },
        }

    def _get_table_field_label_cache(self, table_name, cache=None):
        cache = cache if cache is not None else {}
        if table_name in cache:
            return cache[table_name]

        table = self._open_table(table_name)
        try:
            label_map = {}
            for field_name in table.field_names:
                label = FIELD_NAMES.get(field_name.lower())
                if not label:
                    continue
                normalized_label = _normalize_label(label)
                normalized_label = PARAMETER_LABEL_ALIASES.get(normalized_label, normalized_label)
                label_map.setdefault(normalized_label, field_name)
            cache[table_name] = label_map
            return label_map
        finally:
            table.close()

    def action_export_to_foxpro(self):
        for sheet in self:
            try:
                if not _clean_text(sheet.analysis_id.codpro):
                    prefix = sheet._get_export_prefix()
                    if _clean_text(sheet.foxpro_article_prefix) != prefix:
                        sheet.write({'foxpro_article_prefix': prefix})
                warning_message = sheet._export_to_foxpro_dbf()
                sheet.write({
                    'foxpro_export_state': 'done',
                    'foxpro_export_message': warning_message or False,
                    'foxpro_export_date': fields.Datetime.now(),
                })
            except Exception as error:
                message = str(error)
                sheet.write({
                    'foxpro_export_state': 'error',
                    'foxpro_export_message': message,
                })
                raise UserError(_('No se pudo exportar la ficha tecnica a DBF: %s') % message) from error
        return True

    def _export_to_foxpro_dbf(self):
        self.ensure_one()
        analysis = self.analysis_id
        if not analysis:
            raise UserError(_('La ficha tecnica debe estar vinculada a un analisis para exportarse.'))

        partner = self.partner_id or analysis.partner_id
        if not partner:
            raise UserError(_('La ficha tecnica no tiene cliente asociado.'))

        if not analysis.product_code:
            raise UserError(_('El analisis no tiene Product Code.'))

        ficha = _clean_text(self.sitpro_sheet) or self._next_foxpro_ficha()
        is_new_sheet = not self._dbf_record_exists('tinto_cab_ruta.dbf', 'FICHA', ficha)
        cdgart = self._get_cdgart()
        cdgclie = self._ensure_cliente(partner)
        weaving_line = analysis.weaving_data_ids.filtered(lambda line: line.technical_sheet_id == self)[:1]
        notes = _clean_text(weaving_line.notes or self.notes or analysis.notes)
        fecha = self.technical_date or analysis.analysis_date or fields.Date.context_today(self)
        process_table_values = self._collect_process_table_values(ficha, fecha)

        self._upsert_single('tinto_cab_ruta.dbf', 'FICHA', ficha, {
            'FICHA': ficha,
            'FECHA': fecha,
            'CDGCLIE': cdgclie,
            'RAZSOC': partner.name,
            'CDGART': cdgart,
            'DESCRIP': analysis.product_description or self.product_id.name,
            'COLOR': '',
            'NUMORDPED': '',
            'VOUCHER': self.name,
            'STYLO': self.stylo,
            'ANCHO': _cab_width_value(self.width or self.raw_width),
            'DENSID': _cab_width_value(self.density or self.raw_density),
        })
        crudo_values = {
            'FICHA': ficha,
            'FECHA': fecha,
            'ANCHO': _dbf_number_text(self.raw_width),
            'DENSIDAD': _dbf_number_text(self.raw_density),
            'ENSANCH': _dbf_number_text(self.raw_widening),
            'TROLLO': _dbf_number_text(self.finish_width),
            'VROLLO': _dbf_number_text(self.finish_density),
            'RROLLO': _dbf_number_text(self.finish_yield),
            'OBS': notes.upper(),
        }
        crudo_values.update(process_table_values.pop('tinto_crudo.dbf', {}))
        self._upsert_single('tinto_crudo.dbf', 'FICHA', ficha, crudo_values)
        self._upsert_single('tinto_tejido.dbf', 'FICHA', ficha, {
            'FICHA': ficha,
            'FECHA': fecha,
            'MAQ': '',
            'GALGA': analysis.gauge_id.code if hasattr(analysis.gauge_id, 'code') else analysis.gauge_id.name,
            'AGUJAS': _dbf_number_text(analysis.needles, digits=0),
            'DIAMETRO': _dbf_number_text(analysis.diameter, digits=0),
            'ALIMENTA': _dbf_number_text(analysis.feeders, digits=0),
            'TIPTEJ': self._get_tiptej(analysis.weave_type),
            'MARCA': '',
            'OBSTEJIDO': notes,
        })

        self._delete_by_ficha('ficha_ruta_final.dbf', ficha)
        self._delete_by_ficha('tinto_prog.dbf', ficha)
        self._sync_process_tables(ficha, process_table_values)

        base_process = analysis.mrp_base_process_id.name or ''
        for index, route_line in enumerate(self.route_line_ids.sorted(key=lambda line: (line.sequence, line.id)), start=1):
            self._append_record('ficha_ruta_final.dbf', {
                'FICHA': ficha,
                'IT': index * 100,
                'FASCOD': base_process,
                'FASDSC': '',
                'FASE': _phase_code(route_line.operation_id.name),
                'FASECOM': route_line.operation_id.name,
            })

        fibers = weaving_line.fiber_ids if weaving_line else self.env['analysis.fiber']
        if not fibers:
            raise UserError(_('La ficha tecnica no tiene fibras para exportar a tinto_prog.'))
        yarn_process_cache = {}
        for item, fiber in enumerate(fibers.sorted(key=lambda line: (line.sequence, line.id)), start=1):
            if not fiber.product_template_id:
                raise UserError(_('Existe una fibra sin hilo asociado en la ficha tecnica.'))
            yarn_code = _clean_text(fiber.product_template_id.default_code)
            if yarn_code not in yarn_process_cache:
                yarn_process_cache[yarn_code] = self._get_yarn_process_data(yarn_code)
            yarn_process = yarn_process_cache[yarn_code]
            self._append_record('tinto_prog.dbf', {
                'FICHA': ficha,
                'FECHA': fecha,
                'ITEM': item,
                'LM': item,
                'ARTICULO': fiber.product_template_id.name,
                'COLOR': '',
                'LOTE': '',
                'PROVEEDOR': '',
                'ALIM': '',
                'CON': '',
                'KG': _dbf_number_text(fiber.weight, digits=6),
                'PORCEN': _dbf_number_text(fiber.percentage * 100),
                'CODIGO': fiber.product_template_id.default_code,
                'IT': None,
                'LIGAMENTO': fiber.ligament_id.name,
                'LM1': _dbf_number_text(fiber.length),
                'CODPRO': yarn_process['codpro'],
                'PROCESO': yarn_process['proceso'],
                'LINEA': yarn_process['linea'],
            })

        texplus_warning = False
        try:
            self._export_to_texplus_sql(cdgart, partner, notes)
        except Exception as error:
            texplus_warning = _('DBF exportado. TEXPLUS pendiente: %s') % error

        if is_new_sheet:
            self._insert_sitpro_hojacorr()

        values = {
            'sitpro_sheet': ficha,
        }
        weaving_data = analysis.weaving_data_ids.filtered(lambda line: line.technical_sheet_id == self)
        if not weaving_data.sitpro_sheet:
            weaving_data.write({'sitpro_sheet': ficha})
        self.write(values)
        return texplus_warning

    def _get_company_dbf_root(self):
        dbf_root = _clean_text(self.company_id.foxpro_dbf_path)
        if not dbf_root:
            raise UserError(_('Configure la ruta DBF de FoxPro en Ajustes.'))
        root = Path(dbf_root)
        if not root.exists() or not root.is_dir():
            raise UserError(_('La ruta DBF configurada no existe o no es un directorio valido: %s') % dbf_root)
        return root

    def _get_export_prefix(self):
        self.ensure_one()
        return _normalize_export_prefix(
            self.env.context.get('foxpro_article_prefix') or self.foxpro_article_prefix
        )

    def _get_cdgart(self):
        self.ensure_one()
        analysis = self.analysis_id
        raw_code = _clean_text(analysis.codpro)
        if not raw_code:
            prefix = self._get_export_prefix()
            raw_code = f'{prefix}{_clean_text(analysis.product_code)}'
        if len(raw_code) != 16:
            raise UserError(_('El codigo a exportar a CDGART debe tener 16 caracteres. Revise CodigoProductoBD o el prefijo guardado. Valor actual: %s') % raw_code)
        return raw_code

    def _get_sql_connection(self):
        try:
            connection = pyodbc.connect(
                "DSN=SITPRO_DSN;"
                "PORT=1433;"
                "UID=sistemas;"
                "PWD=idtE#21@IRdc95;"
                "TDS_Version=7.3;"
                ,
                timeout=5,
            )
            connection.timeout = 10
            return connection
        except Exception as error:
            raise UserError(_('No se pudo conectar a SQL Server: %s') % error) from error

    def _get_texplus_sql_connection(self):
        try:
            connection = pyodbc.connect(
                "DSN=ENBTEX1_DSN;"
                "PORT=1433;"
                "UID=sistemas;"
                "PWD=idtE#21@IRdc95;"
                "TDS_Version=7.3;"
                ,
                timeout=5,
            )
            connection.timeout = 10
            return connection
        except Exception as error:
            raise UserError(_('No se pudo conectar a TEXPLUS SQL Server: %s') % error) from error

    def _export_to_texplus_sql(self, article_code, partner, notes):
        self.ensure_one()
        route_code = self._get_texplus_route_code()
        route_description = self._get_texplus_route_description()
        warnings = []

        master_error = self._export_texplus_master_data(article_code, partner, notes)
        if master_error:
            warnings.append(_('maestro de producto pendiente: %s') % master_error)

        route_error = self._export_texplus_route_data(route_code, route_description)
        if route_error:
            warnings.append(_('rutas pendientes: %s') % route_error)

        article_route_error = self._export_texplus_article_processes(article_code, route_code)
        if article_route_error:
            warnings.append(_('fases de articulo pendientes: %s') % article_route_error)

        if warnings:
            return _('TEXPLUS con pendientes: %s') % ' | '.join(warnings)
        return False

    def _configure_texplus_cursor(self, cursor):
        cursor.execute('SET LOCK_TIMEOUT 5000')
        cursor.execute('SET ARITHABORT ON')

    def _export_texplus_master_data(self, article_code, partner, notes):
        conn = None
        cursor = None
        try:
            conn = self._get_texplus_sql_connection()
            cursor = conn.cursor()
            self._configure_texplus_cursor(cursor)
            client_code = 1
            self._upsert_texplus_articu(cursor, article_code, client_code, notes)
            self._upsert_texplus_artlin(cursor, article_code, client_code)
            conn.commit()
            return False
        except UserError:
            if conn:
                conn.rollback()
            raise
        except Exception as error:
            if conn:
                conn.rollback()
            return _clean_text(error)
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

    def _export_texplus_route_data(self, route_code, route_description):
        conn = None
        cursor = None
        try:
            conn = self._get_texplus_sql_connection()
            cursor = conn.cursor()
            self._configure_texplus_cursor(cursor)
            self._upsert_texplus_route_headers(cursor, route_code, route_description)
            conn.commit()
        except UserError:
            if conn:
                conn.rollback()
            raise
        except Exception as error:
            if conn:
                conn.rollback()
            return _clean_text(error)
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

        process_error = self._export_texplus_route_process_data(route_code)
        if process_error:
            return process_error
        return False

    def _export_texplus_route_process_data(self, route_code):
        conn = None
        cursor = None
        try:
            conn = self._get_texplus_sql_connection()
            cursor = conn.cursor()
            self._configure_texplus_cursor(cursor)
            self._replace_texplus_route_processes(cursor, route_code)
            conn.commit()
            return False
        except UserError:
            if conn:
                conn.rollback()
            raise
        except Exception as error:
            if conn:
                conn.rollback()
            return _clean_text(error)
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

    def _export_texplus_article_processes(self, article_code, route_code):
        conn = None
        cursor = None
        try:
            conn = self._get_texplus_sql_connection()
            cursor = conn.cursor()
            self._configure_texplus_cursor(cursor)
            client_code = 1
            self._replace_texplus_article_processes(cursor, article_code, client_code, route_code)
            conn.commit()
            return False
        except UserError:
            if conn:
                conn.rollback()
            raise
        except Exception as error:
            if conn:
                conn.rollback()
            return _clean_text(error)
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

    def _get_texplus_route_code(self):
        route_code = _clean_text(self.analysis_id.mrp_base_process_id.name)
        if not route_code:
            raise UserError(_('La ficha tecnica no tiene un codigo de ruta base para exportar a TEXPLUS.'))
        if len(route_code) > 8:
            raise UserError(_('El codigo de ruta TEXPLUS no puede exceder 8 caracteres. Valor actual: %s') % route_code)
        return route_code

    def _get_texplus_route_description(self):
        operations = [
            _clean_text(line.operation_id.name)
            for line in self.route_line_ids.sorted(key=lambda line: (line.sequence, line.id))
            if _clean_text(line.operation_id.name)
        ]
        short_description = ', '.join(operations)[:40]
        long_description = ', '.join(operations)[:100]
        return {
            'short': short_description,
            'long': long_description,
        }

    def _get_texplus_phase_code(self, route_line):
        phase_code = _clean_text(route_line.operation_id.fas_code)
        if not phase_code:
            raise UserError(
                _('La operacion %s no tiene Codigo MSSQL (fas_code). Sin ese codigo no se puede exportar a TEXPLUS.')
                % route_line.operation_id.name
            )
        if len(phase_code) > 8:
            raise UserError(_('El Codigo MSSQL de la operacion %s excede 8 caracteres: %s') % (route_line.operation_id.name, phase_code))
        return phase_code

    def _get_texplus_fabric_composition(self):
        """Return the TIPART code to export to TEXPLUS.

        The composition is now chosen in Odoo via `fabric_composition_id`
        (a row of the local TIPART mirror), so there is no need to search or
        create rows in TEXPLUS — we just send the code. Falls back to 1
        ('X DEFINIR') when no composition is set.
        """
        return self.fabric_composition_id.tipart_cod or 1

    def _upsert_texplus_articu(self, cursor, article_code, client_code, notes):
        finish_width = _texplus_int(self.width or self.finish_width)
        finished_weight = _texplus_int(self.density or self.finish_density)
        technical_date = self.technical_date or self.analysis_id.analysis_date or fields.Date.context_today(self)
        values = {
            'EmprCod': TEXPLUS_EMPRCOD,
            'CliCod': client_code,
            'ArtCod': article_code,
            'TipArtCod': self._get_texplus_fabric_composition(),
            'ArtDsc': _dbf_char(self.analysis_id.product_description or self.product_id.name, max_len=26),
            'ArtGraCru': _texplus_int(self.density),
            'ArtGraAca': finished_weight,
            'ArtAcaMin': finish_width,
            'ArtAncSal1': _texplus_int(self.width or self.finish_width),
            'ArtTipPle': _dbf_char(self._get_tiptej(self.weave_type), max_len=10),
            'ArtRdoA': _texplus_decimal(self.yield_meter),
            'ArtObs': _dbf_char(notes, max_len=60),
            'ArtObsLon': notes or '',
            'ArtFecCre': technical_date,
        }
        key_values = {
            'EmprCod': TEXPLUS_EMPRCOD,
            'CliCod': client_code,
            'ArtCod': article_code,
        }
        self._upsert_texplus_record(cursor, 'ARTICU', key_values, values)

    def _upsert_texplus_artlin(self, cursor, article_code, client_code):
        values = {
            'EmprCod': TEXPLUS_EMPRCOD,
            'CliCod': client_code,
            'ArtCod': article_code,
            'ProCod': self._get_texplus_route_code(),
            'Art_GrmA': _texplus_int(self.finish_density or self.density),
            'Art_AncA': _texplus_int(self.finish_width or self.width),
            'Art_Rdo': _texplus_decimal(self.finish_yield),
            'Art_Dsc': _dbf_char(self.analysis_id.product_description or self.product_id.name, max_len=26),
            'Art_Obs': self.notes or '',
            'ProAct': 'S',
        }
        key_values = {
            'EmprCod': TEXPLUS_EMPRCOD,
            'CliCod': client_code,
            'ArtCod': article_code,
        }
        self._upsert_texplus_record(cursor, 'ARTLIN', key_values, values)

    def _upsert_texplus_route_headers(self, cursor, route_code, route_description):
        values = {
            'EmprCod': TEXPLUS_EMPRCOD,
            'ProCod': route_code,
            'ProDsc': _dbf_char(route_description['short'], max_len=40),
            'ProUltLin': 0,
            'ProDsc2': _dbf_char(route_description['long'], max_len=100),
        }
        key_values = {
            'EmprCod': TEXPLUS_EMPRCOD,
            'ProCod': route_code,
        }
        for table_name in TEXPLUS_ROUTE_TABLES:
            self._upsert_texplus_record(cursor, table_name, key_values, values)

    def _replace_texplus_route_processes(self, cursor, route_code):
        cursor.execute('DELETE FROM dbo.Texplus_Ruta_Proceso WHERE Cod_Ruta = ?', route_code)
        for index, route_line in enumerate(self.route_line_ids.sorted(key=lambda line: (line.sequence, line.id)), start=1):
            cursor.execute(
                """
                INSERT INTO dbo.Texplus_Ruta_Proceso (Cod_Ruta, Orden, Proceso, Dsc_Proceso)
                VALUES (?, ?, ?, ?)
                """,
                route_code,
                index * 100,
                self._get_texplus_phase_code(route_line),
                _dbf_char(route_line.operation_id.name, max_len=28),
            )

    def _replace_texplus_article_processes(self, cursor, article_code, client_code, route_code):
        cursor.execute(
            'DELETE FROM dbo.SERPAU WHERE EmprCod = ? AND CliCod = ? AND ArtCod = ? AND ProCod = ?',
            TEXPLUS_EMPRCOD,
            client_code,
            article_code,
            route_code,
        )
        for route_line in self.route_line_ids.sorted(key=lambda line: (line.sequence, line.id)):
            cursor.execute(
                """
                INSERT INTO dbo.SERPAU (EmprCod, CliCod, ArtCod, ProCod, FasCod)
                VALUES (?, ?, ?, ?, ?)
                """,
                TEXPLUS_EMPRCOD,
                client_code,
                article_code,
                route_code,
                self._get_texplus_phase_code(route_line),
            )

    def _upsert_texplus_record(self, cursor, table_name, key_values, values):
        update_values = {field_name: value for field_name, value in values.items() if field_name not in key_values}
        where_clause = ' AND '.join(f'[{field_name}] = ?' for field_name in key_values)
        if update_values:
            set_clause = ', '.join(f'[{field_name}] = ?' for field_name in update_values)
            cursor.execute(
                f'UPDATE dbo.{table_name} SET {set_clause} WHERE {where_clause}',
                *update_values.values(),
                *key_values.values(),
            )
            if cursor.rowcount:
                return
        insert_fields = list(values)
        placeholders = ', '.join('?' for _field_name in insert_fields)
        cursor.execute(
            f"INSERT INTO dbo.{table_name} ({', '.join(f'[{field_name}]' for field_name in insert_fields)}) VALUES ({placeholders})",
            *[values[field_name] for field_name in insert_fields],
        )

    def _get_yarn_process_data(self, yarn_code):
        yarn_code = _clean_text(yarn_code)
        if not yarn_code:
            return {'codpro': '', 'proceso': '', 'linea': ''}

        conn = None
        cursor = None
        try:
            conn = self._get_sql_connection()
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT TOP 1
                    c.proceso AS codpro,
                    hp.proceso AS proceso,
                    hl.linea AS linea
                FROM codigohilocrud c
                INNER JOIN hil_proceso hp ON c.proceso = hp.cdgproceso
                INNER JOIN hil_linea hl ON c.linea = hl.cdglinea
                WHERE c.codigo = ?
                """,
                yarn_code,
            )
            row = cursor.fetchone()
            if not row:
                return {'codpro': '', 'proceso': '', 'linea': ''}
            return {
                'codpro': _clean_text(row.codpro),
                'proceso': _clean_text(row.proceso),
                'linea': _clean_text(row.linea),
            }
        except UserError:
            raise
        except Exception as error:
            raise UserError(
                _('No se pudo obtener proceso y linea del hilo %s desde SQL Server: %s') % (yarn_code, error)
            ) from error
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

    def _insert_sitpro_hojacorr(self):
        """Append a new correlative row to the hojacorr.dbf table.

        hojacorr is a FoxPro DBF (not a SQL table): we read the current
        max(correl), then append a record with max+1. Returns the new value.
        """
        try:
            table = self._open_table('hojacorr.dbf')
        except UserError:
            raise
        except Exception as error:
            raise UserError(_('No se pudo abrir hojacorr.dbf: %s') % error) from error
        try:
            correl_field = next(
                (name for name in table.field_names if name.upper() == 'CORREL'),
                None,
            )
            if not correl_field:
                raise UserError(_('hojacorr.dbf no tiene la columna CORREL.'))
            max_correl = 0
            for record in table:
                if dbf.is_deleted(record):
                    continue
                value = record[correl_field]
                if value:
                    max_correl = max(max_correl, int(value))
            new_correl = max_correl + 1
            self._append_record_with_table(table, {correl_field: new_correl})
            return new_correl
        except UserError:
            raise
        except Exception as error:
            raise UserError(_('No se pudo insertar correlativo en hojacorr.dbf: %s') % error) from error
        finally:
            table.close()

    def _get_tiptej(self, weave_type):
        mapping = {
            'open': 'ABIERTO',
            'tubu': 'TUBULAR',
            'rect': 'RECTILINEO',
            'othe': 'OTRO',
        }
        return mapping.get(weave_type, 'ABIERTO')

    def _get_process_table_name(self, operation_name):
        operation_name = _clean_text(operation_name)
        for item in PROCESS_TABLES:
            if operation_name in item['process']:
                return item['table']
        return False

    def _get_parameter_dbf_field(self, table_name, parameter_name, cache=None):
        parameter_label = _normalize_label(parameter_name)
        parameter_label = PARAMETER_LABEL_ALIASES.get(parameter_label, parameter_label)
        return self._get_table_field_label_cache(table_name, cache=cache).get(parameter_label, False)

    def _collect_process_table_values(self, ficha, fecha):
        process_table_values = {}
        table_field_cache = {}
        for route_line in self.route_line_ids.sorted(key=lambda line: (line.sequence, line.id)):
            table_name = self._get_process_table_name(route_line.operation_id.name)
            if not table_name:
                continue
            values = process_table_values.setdefault(table_name, {
                'FICHA': ficha,
                'FECHA': fecha,
            })
            for parameter in route_line.line_parameter_ids:
                field_name = self._get_parameter_dbf_field(table_name, parameter.name, cache=table_field_cache)
                if not field_name:
                    continue
                parameter_value = parameter.value
                if parameter_value in (False, None, ''):
                    continue
                if field_name not in values or values[field_name] in (False, None, ''):
                    values[field_name] = parameter_value
        return process_table_values

    def _sync_process_tables(self, ficha, process_table_values):
        for item in PROCESS_TABLES:
            table_name = item['table']
            if table_name == 'tinto_crudo.dbf':
                continue
            values = process_table_values.get(table_name)
            if values:
                self._upsert_single(table_name, 'FICHA', ficha, values)
            else:
                self._delete_by_ficha(table_name, ficha)

    def _table_path(self, filename):
        return self._get_company_dbf_root() / filename

    def _open_table(self, filename):
        path = self._table_path(filename)
        if not path.exists():
            raise UserError(_('No existe la tabla DBF requerida: %s') % path)
        table = dbf.Table(str(path), codepage='cp1252')
        # table = dbf.VfpTable(str(path), codepage='cp1252')
        table.open(mode=dbf.READ_WRITE)
        return table

    def _next_foxpro_ficha(self):
        self.ensure_one()
        year_suffix = str((self.technical_date or fields.Date.context_today(self)).year)[-2:]
        table = self._open_table('tinto_cab_ruta.dbf')
        try:
            max_seq = 0
            pattern = re.compile(r'^(\d{5})-(\d{2})$')
            for record in table:
                if dbf.is_deleted(record):
                    continue
                ficha = _clean_text(record['FICHA'])
                match = pattern.match(ficha)
                if not match or match.group(2) != year_suffix:
                    continue
                max_seq = max(max_seq, int(match.group(1)))
            return f'{max_seq + 1:05d}-{year_suffix}'
        finally:
            table.close()

    def _find_cliente_codigo(self, table, vat):
        target_vat = self._normalize_key_value(table, 'RUC', vat)
        if not _clean_text(target_vat):
            return False
        for record in table:
            if dbf.is_deleted(record):
                continue
            if record['RUC'] == target_vat:
                return _clean_text(record['CDGCLIE'])
        return False

    def _next_cliente_codigo(self, table, partner_name):
        letter = _clean_text(partner_name)[:1].upper() or 'C'
        pattern = re.compile(r'^%s(\d{4})$' % re.escape(letter))
        max_seq = 0
        for record in table:
            if dbf.is_deleted(record):
                continue
            code = _clean_text(record['CDGCLIE']).upper()
            match = pattern.match(code)
            if match:
                max_seq = max(max_seq, int(match.group(1)))
        return f'{letter}{max_seq + 1:04d}'

    def _ensure_cliente(self, partner):
        table = self._open_table('clientes.dbf')
        try:
            existing_code = self._find_cliente_codigo(table, partner.vat)
            values = {
                'RAZSOC': partner.name,
                'RUC': partner.vat,
                'DIRECCI': partner.street,
                'PAIS': partner.country_id.name,
                'DESDIS': getattr(partner, 'l10n_pe_district', False) and partner.l10n_pe_district.name or '',
                'DPTO': partner.state_id.name,
                'DIRDESP': partner.street,
                'PAISDESP': partner.country_id.name,
                'DISDESP': getattr(partner, 'l10n_pe_district', False) and partner.l10n_pe_district.name or '',
                'DPTODESP': partner.state_id.name,
                'DIRCOB': partner.street,
                'PAISCOB': partner.country_id.name,
                'DISCOB': getattr(partner, 'l10n_pe_district', False) and partner.l10n_pe_district.name or '',
                'DPTOCOB': partner.state_id.name,
                'TELEF1': partner.phone,
                'EMAIL': partner.email,
                'OBSCLIEN': '',
                'CONTACTOVT': (self.env.user.login or self.env.user.name or '')[:4],
                'USUARIO': self.env.user.name,
                'ACTIVO': True,
            }
            if existing_code:
                values['CDGCLIE'] = existing_code
                self._update_record(table, 'CDGCLIE', existing_code, values)
                return existing_code

            code = self._next_cliente_codigo(table, partner.name)
            values['CDGCLIE'] = code
            self._append_record_with_table(table, values)
            return code
        finally:
            table.close()

    def _upsert_single(self, filename, key_field, key_value, values):
        table = self._open_table(filename)
        try:
            if not self._update_record(table, key_field, key_value, values):
                self._append_record_with_table(table, values)
        finally:
            table.close()

    def _dbf_record_exists(self, filename, key_field, key_value):
        table = self._open_table(filename)
        try:
            target = self._normalize_key_value(table, key_field, key_value)
            for record in table:
                if dbf.is_deleted(record):
                    continue
                if record[key_field] == target:
                    return True
            return False
        finally:
            table.close()

    def _update_record(self, table, key_field, key_value, values):
        target = self._normalize_key_value(table, key_field, key_value)
        for record in table:
            if dbf.is_deleted(record):
                continue
            if record[key_field] != target:
                continue
            with record:
                for field_name, value in self._filter_values_for_table(table, values).items():
                    record[field_name] = value
            return True
        return False

    def _delete_by_ficha(self, filename, ficha):
        table = self._open_table(filename)
        try:
            target = self._normalize_key_value(table, 'FICHA', ficha)
            for record in table:
                if dbf.is_deleted(record):
                    continue
                if record['FICHA'] == target:
                    dbf.delete(record)
        finally:
            table.close()

    def _append_record(self, filename, values):
        table = self._open_table(filename)
        try:
            self._append_record_with_table(table, values)
        finally:
            table.close()

    def _append_record_with_table(self, table, values):
        table.append(self._filter_values_for_table(table, values))

    def _filter_values_for_table(self, table, values):
        filtered = {}
        field_names = set(table.field_names)
        for field_name, value in values.items():
            if field_name not in field_names:
                continue
            filtered[field_name] = self._coerce_dbf_value(table, field_name, value)
        return filtered

    def _coerce_dbf_value(self, table, field_name, value):
        field_type, size, decimals, python_type = table.field_info(field_name)
        if value in (False, None):
            if python_type in (str,):
                return ''
            if python_type in (int, float):
                return 0
            return False if python_type is bool else value

        if python_type is str and field_name in PADR_FIELDS:
            return _dbf_padr(value, size)
        if python_type is str and _is_memo_field(field_type):
            return _clean_text(value)
        if python_type is str:
            return _dbf_char(value, max_len=size)
        if python_type is int:
            return int(value)
        if python_type is float:
            return float(value)
        if python_type is bool:
            return bool(value)
        return value

    def _normalize_key_value(self, table, field_name, value):
        field_type, size, decimals, python_type = table.field_info(field_name)
        if python_type is str and field_name in PADR_FIELDS:
            return _dbf_padr(value, size)
        return _clean_text(value)
