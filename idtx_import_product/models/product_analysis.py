# -*- coding: utf-8 -*-
import datetime
import re
import unicodedata
import pyodbc
pyodbc.setDecimalSeparator(".")
from odoo import models, fields, api, _
from odoo.fields import Command
from odoo.exceptions import UserError

import logging
_logger = logging.getLogger(__name__)

TERMO_2 = []
MCS = []
ABI_TER = ['Ancho de Entrada', 'Densidad de Entrada','Ancho de Cadena','Velocidad','Temperatura C°','Alimentador Superior','Alimentador Inferior','Alimentador de Salida','Presión','Ancho de Salida','Densidad de Salida','Alimentador Brazo Derecho','Alimentador Brazo Izquierdo','Presión Foulard','T° por Campos','Turbulencia','Inclinación de Trama','Maquina']
ABI_SIL = []
ABI_RAMA = []
ABI_PERCHA = []
ABI_TUNDI = []
ABI_ESME = []
ABI_TAM = []
ABI_ABRI = []
ABI_HIDRO = []
ABI_SECA = []
ABI_COMPA = []
CALIDAD = []
TABLES = [
    {'process': ['TEJIDO CRUDO','SERV. TEJIDO'], 'table': 'tinto_crudo'},
    {'process': ['THERMOFIJADO ENTEMA','THERMOFIJADO MERSAN'], 'table': 'tinto_termo_2'},
    #'tinto_mcs', Segun alex esto no se llena, es complejo y lo hace tintoreri}a
    {'process': ['THERMOFIJADO RAMA','THERMOFIJADO DISPERSANTE/HUM','THERMO-BLANQUEO ACABADO','THERMO ACABADO'], 'table': 'tinto_abi_ter'},
    {'process': ['SECADO','SECADO RECETA 155','SECADO PP ESTAMPAR','SECADO LUBRICANTE COSTURA','SECADO SOLO AGUA','SECADO PP ESMERILAR','SECADO PP PERCHAR','SECADO INCLINACION FULL','SECADO RECETA 211','SECADO PP TEÑIR','SECADO ENGOMADO C/ORILLOS',], 'table': 'tinto_abi_sil'},
    {'process': ['ACABADO','ACAB RESINA LIBRE FORMALEHID','ACABADO RESINADO','PRESECADO 100% RESINADO 158','ACABADO RECETA 104','ACABADO RECETA 102','ACABADO RECETA 157','PRESECADO 100% RESINADO 71','ACABADO RECETA 156','PRESECADO 100% ACABADO 157','ACABADO WICKING','ACABADO LUBRICANTE COSTURA','ACABADO HIDROFILO TACTO SUAV','ACABADO LUXURY','ACABADO BESOCOOL','ACABADO RESINADO LUXURY','ACABADO CON CORTE DE ORILLOS','PRESECADO 50% SOLO AGUA','PRESECADO 100% ACABADO','PRESECADO100% ACA157 ENG/C O','ACABADO RESINADO 1/2 RECETA','ACABADO RESI LUXU RECETA 158','ACABADO RESINADO LANDS END','PRESECADO 100% ACABADO 104','ACABADO RESINADO C/ORILLOS','ACABADO ENGOMADO C/ORILLOS','RAMA ENGOMADO/CORTE ORILLOS','RAMA CON HUMECTANTE','SUAVIZADO PP PERCHAR','ACABADO RECETA 101','ACABADO RESINADO LACOSTE','ACABADO WICKING RECETA 76','ACABADO RECETA 120','ACABADO PIQUE TACTO LACOSTE','ACAB RESIN LUXURY 1/2 RECETA','ACABADO RECETA 209','ACABADO ENGOMADO','ACABADO SOLO AGUA SIN C/ORIL','ACABADO HIDROFILO','LAVADO Y ACABADO ROTOCLEAN','ACABADO RESI LUXURY POLYCRYL','ACABADO PP SUBLIMAR','ACABADO WICKING+ANTIMICROBIA'], 'table': 'tinto_abi_rama'},
    {'process': ['PERCHADORA','PERCHADO X REVEZ','PERCHADO 2 PASES'], 'table': 'tinto_abi_percha'},
    {'process': ['TUNDIDO SOLO PUNTAS','TUNDIDO'], 'table': 'tinto_abi_tundi'},
    {'process': ['ESMERILADO','ESMERILADO X CARA ESTAMPADA','ESMERILADO X CARA'], 'table': 'tinto_abi_esme'},
    {'process': ['TAMBLEADO'], 'table': 'tinto_abi_tam'},
    {'process': ['ABIERTO TINTO','ABRIDORA CON DUCHA 2 PASES'], 'table': 'tinto_abi_abri'},
    {'process': ['HIDROEXTRACTORA','HIDRO SUAVIZADO','HIDRO SUAVIZADO PIMA','HIDRO HUMECTADO','HIDRO SOLO AGUA MINIMA PRESI','HIDRO RESINADO','HIDRO SOLO SUAVIZANT COSTURA','HIDRO SUAVIZANTE PERCHADO','HIDRO SUAVIZADO LUXURY','HIDRO RESINADO LANDS SEND','HIDRO HIDROFILO TACTO SUAVE','HIDRO SUA HIDROFIL TACTO SUA','HIDRO EXPRIMIDO'], 'table': 'tinto_tub_hidro'},
    {'process': ['SECADO','SECADO TUBULAR'], 'table': 'tinto_tub_seca'},
    {'process': ['COMPACTADO','SANFORIZADO'], 'table': 'tinto_tub_compa'},
    {'process': ['CONTROL DE CALIDAD'], 'table': 'tinto_calidad'},
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
    'anchoentra': 'Anch de Entrada',
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
    'otros': 'Otros',
    'temperatur': 'Temperatura',
    'alimen': 'Alimentación',
    'densientra': 'Densidad de Entrada',
    'densisale': 'Densidad de Salida',
    'tensiing': 'Tensión de Entrada',
    'tensisal': 'Tensión de Salida',
    'obs': 'Observación'
}

def validar_ruc_peru(ruc):
    # Debe ser string de 11 dígitos numéricos
    if not ruc.isdigit() or len(ruc) != 11:
        return False

    # Prefijos válidos según SUNAT
    if ruc[:2] not in {'10', '15', '16', '17', '20'}:
        return False

    # Pesos oficiales
    pesos = [5, 4, 3, 2, 7, 6, 5, 4, 3, 2]

    suma = sum(int(ruc[i]) * pesos[i] for i in range(10))
    resto = suma % 11
    digito = 11 - resto

    if digito == 10:
        digito = 0
    elif digito == 11:
        digito = 1

    return digito == int(ruc[-1])


def a_float(cadena):
    if not isinstance(cadena, str):
        return 0

    match = re.search(r'[-+]?\d*\.?\d+', cadena)
    return float(match.group()) if match else 0
import re

def a_int(cadena):
    if not isinstance(cadena, str):
        return 0
    match = re.search(r'[-+]?\d*\.?\d+', cadena)
    if not match:
        return 0
    return int(float(match.group()))

# ---------- Models ----------
class ProductAnalysis(models.Model):
    _inherit = 'product.analysis'

    is_problem = fields.Boolean('is_problem?')
    state = fields.Selection(selection_add=[('impo', 'Imported')],)
    sitpro_code = fields.Char('sitpro_code') 
    
    @api.onchange('product_code','partner_id')
    def _onchange_is_problem(self):
        for rec in self:
            if not rec.partner_id or not rec.product_family_id or not rec.product_appearance_id or not rec.product_fiber_id or not rec.product_title_id or not rec.gauge_id:
                rec.is_problem = True
            else:
                rec.is_problem = False

    # -----------------------------------------
    # 🔌 CONEXION SQL SERVER
    # -----------------------------------------
    def _get_sql_connection(self):
        try:
            conn = pyodbc.connect(
                "DSN=SITPRO_DSN;"
                "PORT=1433;"
                "UID=sistemas;"
                "PWD=idtE#21@IRdc95;"
                "TDS_Version=7.3;"
            )
            return conn
        except Exception as e:
            raise UserError(f"No se pudo conectar a SQL Server: {e}")

    def _get_texplus_sql_connection(self):
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
            raise UserError(f"No se pudo conectar a TEXPLUS SQL Server: {e}")

    def _texplus_uom(self, value):
        return {
            1: 'gxl',
            3: 'por',
        }.get(a_int(value), 'gxl')

    def _iter_chunked(self, items, size):
        for start in range(0, len(items), size):
            yield items[start:start + size]

    def _get_or_create_texplus_product(self, product_code, product_name, product_cache):
        product_code = (product_code or '').strip()
        if not product_code:
            return False
        product = product_cache.get(product_code)
        if product is not None:
            return product
        product = self.env['product.template'].search([('default_code', '=', product_code)], limit=1)
        if not product:
            product = self.env['product.template'].create({
                'name': (product_name or '').strip() or product_code,
                'default_code': product_code,
                'categ_id': self.env.ref('idtx_laboratory.product_categ_3').id,
                'uom_id': self.env.ref('uom.product_uom_kgm').id,
                # 'uom_po_id': self.env.ref('uom.product_uom_kgm').id,
            })
        product_cache[product_code] = product
        return product

    def _get_or_create_texplus_base_process(self, process_name, base_process_cache):
        process_name = (process_name or '').strip()
        if not process_name:
            return False
        base_process = base_process_cache.get(process_name)
        if base_process is not None:
            return base_process
        base_process = self.env['base.process'].search([('name', '=', process_name)], limit=1)
        if not base_process:
            base_process = self.env['base.process'].create({'name': process_name})
        base_process_cache[process_name] = base_process
        return base_process

    def _build_texplus_recipe_commands(self, texplus_recipe, product_cache=None, base_process_cache=None):
        if not texplus_recipe:
            return []

        product_cache = product_cache if product_cache is not None else {}
        base_process_cache = base_process_cache if base_process_cache is not None else {}
        commands = []

        for process_data in texplus_recipe['processes']:
            base_process = self._get_or_create_texplus_base_process(process_data['process_name'], base_process_cache)
            line_commands = []
            for line_data in process_data['lines']:
                product = self._get_or_create_texplus_product(
                    line_data['product_code'],
                    line_data['product_name'],
                    product_cache,
                )
                line_commands.append(Command.create({
                    'product_id': product.id if product else False,
                    'factor': float(line_data['factor'] or 0.0),
                    'uom': self._texplus_uom(line_data['uom_code']),
                }))

            commands.append(Command.create({
                'base_process_id': base_process.id if base_process else False,
                'color_recipe_process_line_ids': line_commands,
            }))
        return commands

    def _load_texplus_recipes_by_color(self, color_code_values):
        if not color_code_values:
            return {}

        recipe_candidates = {}
        texplus_conn = None
        texplus_cursor = None
        try:
            texplus_conn = self._get_texplus_sql_connection()
            texplus_cursor = texplus_conn.cursor()
            sorted_codes = sorted({str(code or '').strip().upper() for code in color_code_values if str(code or '').strip()})

            for chunk in self._iter_chunked(sorted_codes, 300):
                placeholders = ', '.join('?' for _ in chunk)
                texplus_cursor.execute(
                    f"""
                        SELECT
                            RIGHT('00000000' + LTRIM(RTRIM(f.ForColNom)), 8) AS color_code,
                            f.ForSer,
                            f.ForColNum,
                            f.ForNumCol,
                            f.ForUltMod,
                            f.ForFec,
                            lf.ProForL,
                            lf.ProForCod,
                            pf.ProForDsc,
                            lp.ProForLin,
                            lp.ProForPrd,
                            lp.ProForDes,
                            lp.ForPrdUMe,
                            lp.ProForCan
                        FROM dbo.CFORMU f
                        LEFT JOIN dbo.LFORMU lf
                            ON lf.EmprCod = f.EmprCod
                           AND lf.ForSer = f.ForSer
                           AND lf.ForColNum = f.ForColNum
                        LEFT JOIN dbo.CPROFO pf
                            ON pf.EmprCod = lf.EmprCod
                           AND pf.ProForCod = lf.ProForCod
                        LEFT JOIN dbo.LPROFO lp
                            ON lp.EmprCod = lf.EmprCod
                           AND lp.ProForCod = lf.ProForCod
                        WHERE f.ForEst = 'S'
                          AND RIGHT('00000000' + LTRIM(RTRIM(f.ForColNom)), 8) IN ({placeholders})
                        ORDER BY color_code, f.ForUltMod DESC, f.ForFec DESC, lf.ProForL, lp.ProForLin
                    """,
                    *chunk,
                )
                columns = [col[0].lower() for col in texplus_cursor.description]
                raw_rows = texplus_cursor.fetchall()
                for raw_row in raw_rows:
                    row = dict(zip(columns, raw_row))
                    color_code = str(row.get('color_code') or '').strip().upper()
                    if not color_code:
                        continue

                    formula_key = (
                        str(row.get('forser') or '').strip(),
                        a_int(row.get('forcolnum')) or 0,
                        a_int(row.get('fornumcol')) or 0,
                    )
                    formulas_for_color = recipe_candidates.setdefault(color_code, {})
                    formula = formulas_for_color.setdefault(formula_key, {
                        'sort_key': (
                            row.get('forultmod') or fields.Datetime.to_datetime('1900-01-01 00:00:00'),
                            row.get('forfec') or fields.Datetime.to_datetime('1900-01-01 00:00:00'),
                            formula_key,
                        ),
                        'process_map': {},
                    })

                    process_code = str(row.get('proforcod') or '').strip()
                    process_name = str(row.get('profordsc') or '').strip() or process_code
                    process_order = a_int(row.get('proforl')) or 0
                    if not process_name:
                        continue

                    process_entry = formula['process_map'].setdefault((process_order, process_code, process_name), {
                        'process_name': process_name,
                        'order': process_order,
                        'line_map': {},
                    })

                    product_code = str(row.get('proforprd') or '').strip()
                    product_name = str(row.get('profordes') or '').strip() or product_code
                    product_order = a_int(row.get('proforlin')) or 0
                    if product_code or product_name:
                        process_entry['line_map'][(product_order, product_code, product_name)] = {
                            'product_code': product_code,
                            'product_name': product_name,
                            'factor': row.get('proforcan') or 0.0,
                            'uom_code': row.get('forprdume'),
                        }
        finally:
            try:
                texplus_cursor.close()
            except Exception:
                pass
            try:
                texplus_conn.close()
            except Exception:
                pass

        selected_recipes = {}
        for color_code, formulas in recipe_candidates.items():
            if not formulas:
                continue
            selected_formula = max(formulas.values(), key=lambda item: item['sort_key'])
            processes = []
            for _, process_data in sorted(selected_formula['process_map'].items(), key=lambda item: item[0]):
                lines = [line_data for _, line_data in sorted(process_data['line_map'].items(), key=lambda item: item[0])]
                processes.append({
                    'process_name': process_data['process_name'],
                    'lines': lines,
                })
            selected_recipes[color_code] = {'processes': processes}
        return selected_recipes

    def sync_lab_recipes_from_texplus(self):
        product_cache = {}
        base_process_cache = {}
        lab_lines = self.env['lab.dev.line'].search([('color_code', '!=', False)])
        target_lines = self.env['lab.dev.line']

        for line in lab_lines:
            if line.color_recipe_ids.filtered('color_recipe_process_ids'):
                continue
            target_lines |= line

        color_codes = {str(line.color_code or '').strip().upper() for line in target_lines if str(line.color_code or '').strip()}
        texplus_recipes_by_color = self._load_texplus_recipes_by_color(color_codes)

        created_recipes = 0
        updated_recipes = 0
        missing_texplus = 0
        skipped_with_recipe = 0
        total = len(target_lines)
        progress_every = max(1000, total // 20) if total else 1000

        for index, line in enumerate(target_lines, 1):
            if index == 1 or index % progress_every == 0 or index == total:
                _logger.info("sync_lab_recipes_from_texplus %s / %s", index, total)

            if line.color_recipe_ids.filtered('color_recipe_process_ids'):
                skipped_with_recipe += 1
                continue

            color_code = str(line.color_code or '').strip().upper()
            texplus_recipe = texplus_recipes_by_color.get(color_code)
            if not texplus_recipe:
                missing_texplus += 1
                continue

            recipe_commands = self._build_texplus_recipe_commands(texplus_recipe, product_cache, base_process_cache)
            if not recipe_commands:
                missing_texplus += 1
                continue

            recipe = line.color_recipe_ids.filtered(lambda rec: not rec.color_recipe_process_ids)[:1]
            if recipe:
                recipe.write({'color_recipe_process_ids': [Command.clear(), *recipe_commands]})
                updated_recipes += 1
            elif not line.color_recipe_ids:
                line.write({
                    'color_recipe_ids': [Command.create({
                        'state': 'approved',
                        'color_recipe_process_ids': recipe_commands,
                    })],
                })
                created_recipes += 1

        message = (
            f"Recetas TEXPLUS: creadas={created_recipes}, "
            f"actualizadas={updated_recipes}, "
            f"sin_formula={missing_texplus}, "
            f"omitidas_con_procesos={skipped_with_recipe}"
        )
        _logger.info(message)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('TEXPLUS'),
                'message': message,
                'type': 'success',
                'sticky': False,
            }
        }
    
    # ---------------------------------------------------------------------
    # TEXPLUS — route lookup (replaces SITPRO Ruta_Detalle).
    # ARTLIN holds (ArtCod, ProCod, CliCod, ProAct). Odoo product_code is the
    # TEXPLUS ArtCod minus its leading character, so we match with RIGHT(ArtCod,15).
    # Texplus_Ruta_Proceso (Cod_Ruta, Orden, Proceso, Dsc_Proceso) gives the
    # ordered phase list for a route. Both queries live in this class so they
    # reuse `_get_texplus_sql_connection`.
    # ---------------------------------------------------------------------
    def _get_texplus_route_map(self, product_codes):
        """Return {15-char product_code: route_code} from ARTLIN.

        Filters to active routes only (ProAct='S'). When several rows match the
        same product (different clients), keeps the most recently touched one
        (ProFecA, then ProFecM).
        """
        codes = sorted({(c or '').strip() for c in product_codes if (c or '').strip()})
        if not codes:
            return {}
        try:
            conn = self._get_texplus_sql_connection()
        except Exception:
            _logger.warning("TEXPLUS unreachable for ARTLIN lookup", exc_info=True)
            return {}
        rows = []
        try:
            cursor = conn.cursor()
            for start in range(0, len(codes), 800):
                chunk = codes[start:start + 800]
                placeholders = ",".join(["?"] * len(chunk))
                cursor.execute(
                    f"""
                    SELECT RIGHT(RTRIM(ArtCod), 15) AS code,
                           RTRIM(ProCod) AS ProCod,
                           COALESCE(ProFecA, ProFecM) AS fecha
                    FROM ARTLIN
                    WHERE ProAct = 'S'
                      AND RIGHT(RTRIM(ArtCod), 15) IN ({placeholders})
                    """,
                    *chunk,
                )
                rows.extend(cursor.fetchall())
        finally:
            try: cursor.close()
            except Exception: pass
            try: conn.close()
            except Exception: pass
        # Dedup: keep latest active route per Odoo product code.
        best = {}
        for code, procod, fecha in rows:
            if not code or not procod:
                continue
            current = best.get(code)
            if current is None or (fecha or datetime.datetime.min) > (current[1] or datetime.datetime.min):
                best[code] = (procod, fecha)
        return {code: data[0] for code, data in best.items()}

    def _get_texplus_route_processes(self, route_codes):
        """Return {route_code: [(orden, fascod, fasdsc), ...]} from Texplus_Ruta_Proceso."""
        codes = sorted({(c or '').strip() for c in route_codes if (c or '').strip()})
        if not codes:
            return {}
        try:
            conn = self._get_texplus_sql_connection()
        except Exception:
            return {}
        by_route = {}
        try:
            cursor = conn.cursor()
            for start in range(0, len(codes), 800):
                chunk = codes[start:start + 800]
                placeholders = ",".join(["?"] * len(chunk))
                cursor.execute(
                    f"""
                    SELECT RTRIM(Cod_Ruta), Orden,
                           RTRIM(Proceso), RTRIM(Dsc_Proceso)
                    FROM Texplus_Ruta_Proceso
                    WHERE Cod_Ruta IN ({placeholders})
                    ORDER BY Cod_Ruta, Orden
                    """,
                    *chunk,
                )
                for cod, orden, fascod, fasdsc in cursor.fetchall():
                    by_route.setdefault(cod, []).append((orden, fascod, fasdsc))
        finally:
            try: cursor.close()
            except Exception: pass
            try: conn.close()
            except Exception: pass
        return by_route

    def _ensure_texplus_base_process(self, route_code, processes_list, operation_cache):
        """Find-or-create mrp.base.process named `route_code` and sync its lines
        from `processes_list` (list of (orden, fascod, fasdsc) tuples).

        Replaces existing lines if the TEXPLUS list differs from what's stored.
        """
        BaseProcess = self.env['mrp.base.process']
        base_process = BaseProcess.search([('name', '=', route_code)], limit=1)
        if not base_process:
            base_process = BaseProcess.create({'name': route_code})

        desired = []
        for orden, fascod, fasdsc in processes_list:
            operation = BaseProcess._get_or_create_operation(fascod, fasdsc, operation_cache)
            if operation:
                desired.append((orden, operation.id))
        if not desired:
            return base_process

        current = [
            (line.sequence, line.operation_id.id)
            for line in base_process.process_ids.sorted(key=lambda l: (l.sequence, l.id))
            if line.operation_id
        ]
        if current == desired:
            return base_process

        commands = [(5, 0, 0)]
        for orden, op_id in desired:
            commands.append((0, 0, {'sequence': orden, 'operation_id': op_id}))
        base_process.with_context(skip_texplus_sync=True).write({'process_ids': commands})
        return base_process

    def _apply_texplus_route_to_analyses(self, analyses=None):
        """For each analysis with a product_code, look up its route in TEXPLUS
        (ARTLIN → Texplus_Ruta_Proceso) and set mrp_base_process_id accordingly.
        Regenerates routing_ids and propagates to related technical sheets.
        Returns the number of analyses whose route changed.
        """
        analyses = (analyses or self).filtered('product_code')
        if not analyses:
            return 0
        code_to_route = self._get_texplus_route_map(analyses.mapped('product_code'))
        if not code_to_route:
            return 0
        route_codes = set(code_to_route.values())
        route_processes = self._get_texplus_route_processes(route_codes)
        operation_cache = {}
        base_process_by_code = {}
        for route_code in route_codes:
            base_process_by_code[route_code] = self._ensure_texplus_base_process(
                route_code, route_processes.get(route_code, []), operation_cache,
            )
        # Ensure TEJIDO CRUDO is the first line of every touched base process.
        touched = self.env['mrp.base.process'].browse([
            bp.id for bp in base_process_by_code.values() if bp
        ])
        if touched:
            touched._ensure_weaving_first_line()
        changed = 0
        for analysis in analyses:
            route_code = code_to_route.get(analysis.product_code)
            if not route_code:
                continue
            new_bp = base_process_by_code.get(route_code)
            if new_bp and analysis._set_base_process_and_propagate(new_bp):
                changed += 1
        return changed

    def _set_base_process_and_propagate(self, new_base_process):
        """Set mrp_base_process_id, rebuild routing_ids, and propagate the new
        operations to the related technical sheets' route_line_ids. Returns
        True when something actually changed."""
        self.ensure_one()
        if not new_base_process or new_base_process == self.mrp_base_process_id:
            return False
        self.mrp_base_process_id = new_base_process
        # Replicate _onchange_mrp_base_process_id manually (onchange does not
        # fire on programmatic writes). The analysis has a constraint that
        # forbids more than one weaving operation; the base process can have
        # several (e.g. TEJIDO CRUDO + ABCRUDO + LIJCRUDO all classify as
        # operation_type='weaving'). Keep only the first weaving line.
        lines = new_base_process.process_ids.sorted(key=lambda l: (l.sequence, l.id))
        weaving_seen = False
        operation_ids = []
        for line in lines:
            op = line.operation_id
            if not op:
                continue
            if op.operation_type == 'weaving':
                if weaving_seen:
                    continue
                weaving_seen = True
            operation_ids.append(op.id)
        self.routing_ids = [Command.clear()] + [
            Command.create({'operation_id': op_id}) for op_id in operation_ids
        ]
        # Replicate the route_line_ids construction used in action_create_technical_sheet.
        for sheet in self.technical_sheet_ids:
            sheet.route_line_ids = [Command.clear()] + [
                Command.create({
                    'operation_id': route.operation_id.id,
                    'line_parameter_ids': [
                        Command.create({'name': param.name})
                        for param in route.operation_id.parameter_ids
                    ],
                })
                for route in self.routing_ids.sorted(key=lambda r: r.sequence)
                if route.operation_id
            ]
        return True

    def action_sync_routes_from_texplus(self):
        """Manual trigger: re-sync routes from TEXPLUS for the selected analyses
        (or all analyses with a product_code when called from the model menu).
        """
        targets = self or self.search([('product_code', '!=', False)])
        changed = self._apply_texplus_route_to_analyses(targets)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Sincronización TEXPLUS'),
                'message': _('Rutas actualizadas en %s análisis.') % changed,
                'sticky': False,
                'type': 'success',
            },
        }

    def get_routing_data(self, ruta):
        try:
            conn = self._get_sql_connection()
            cursor = conn.cursor()
            query = f"""
                SELECT *
                FROM Ruta_Detalle
                where procod = '{ruta}'
                ORDER BY
                    Procod,
                    pronumlin;
            """
            cursor.execute(query)
            return cursor.fetchall()
        finally:
            try:
                cursor.close()
            except Exception:
                pass
            try:
                conn.close()
            except Exception:
                pass
    
    def get_parameters_data(self, ficha, table):
        try:
            conn = self._get_sql_connection()
            cursor = conn.cursor()
            query = f"""
                SELECT *
                FROM {table} where ficha = '{ficha}'
            """
            cursor.execute(query)
            columns = [col[0] for col in cursor.description]
            rows = cursor.fetchall()

            # Convertimos a lista de dicts
            return [dict(zip(columns, row)) for row in rows]
        
            # cursor.execute(query)
            # return cursor.fetchall()
        finally:
            try:
                cursor.close()
            except Exception:
                pass
            try:
                conn.close()
            except Exception:
                pass

    # ----- Sync -----
    def sync_from_sql(self):
        try:
            conn = self._get_sql_connection()
            cursor = conn.cursor()
            query = f"""
                SELECT *
                FROM tinto_cab_ruta tcr
                JOIN tinto_crudo tc ON tcr.ficha = tc.ficha
                JOIN tinto_tejido tt ON tcr.ficha = tt.ficha
                JOIN clientes c ON c.cdgclie = tcr.cdgclie
                JOIN (SELECT ficha, fascod, max(it) as it FROM ficha_ruta_final GROUP BY ficha, fascod) frf ON frf.ficha = tcr.ficha
                JOIN (
                    SELECT
                        ficha,
                        item,
                        articulo,
                        MAX(porcen)    AS porcen,
                        MAX(codigo)    AS codigo,
                        MAX(it)        AS it,
                        MAX(ligamento) AS ligamento,
                        MAX(lm1)       AS lm1
                    FROM tinto_prog
                    GROUP BY
                        ficha,
                        item,
                        articulo
                ) TP 
                    ON tcr.ficha = tp.ficha
                WHERE tcr.fecha >= '2000-01-01'
                -- and tcr.ficha = '19497-26'
                and len(tcr.cdgart) = 16
                ORDER BY
                    tcr.fecha desc,
                    tcr.ficha,
                    tp.item;
            """
            cursor.execute(query)
            
            last_weaving_data_id = self.env['analysis.weaving.data']
            cursor_result = cursor.fetchall()
            total = len(cursor_result)
            weaving_workcenter = self.env['mrp.workcenter'].search([('name','=','TEJEDURIA')])
            if not weaving_workcenter:
                weaving_workcenter = self.env['mrp.workcenter'].create({'name': 'TEJEDURIA', 'operation_type': 'weaving'})
            weaving_process = self.env['mrp.routing.workcenter.operation'].search([('name','=','TEJIDO CRUDO')])
            if not weaving_process:
                weaving_process = self.env['mrp.routing.workcenter.operation'].create({'name': 'TEJIDO CRUDO', 'workcenter_id': weaving_workcenter.id})
            for contador, row in enumerate(cursor_result, 1):
                _logger.info(str(contador) + ' / ' + str(total) + '  ' + str(int((contador / total)*100)) + '%')
                if self.env['technical.sheet'].search([('sitpro_sheet','=',row.ficha.strip())]):
                    continue
                code = row.cdgart.strip()
                product_analysis = self.search([('product_code','=', code[1:])])
                partner = self.env['res.partner'].search([('vat','=', row.ruc.strip()),('is_company','=', True)])
                if len(partner) > 1:
                    partner = partner[0]
                if not partner:
                    if len(row.ruc.strip()) == 11 and validar_ruc_peru(row.ruc.strip()):
                        partner = self.env['res.partner'].create({
                            'name': row.razsoc.strip(),
                            'vat': row.ruc.strip(),
                            'l10n_latam_identification_type_id': self.env.ref('l10n_pe.it_RUC').id,
                            'is_company': True,
                        })
                    else:
                        partner = self.env['res.partner'].create({
                            'name': row.razsoc.strip(),
                            'vat': row.ruc.strip(),
                            # 'l10n_latam_identification_type_id': self.env.ref('l10n_pe.it_RUC').id,
                            'is_company': True,
                        })
                if not product_analysis:
                    fam = self.env['product.family'].search([('code','=', code[1:3])])
                    app = self.env['product.appearance'].search([('code','=', code[8:10])])
                    fib = self.env['product.fiber'].search([('code','=', code[5:6])])
                    tit = self.env['product.title'].search([('code','=', code[3:5])])
                    gau = self.env['product.gauge'].search([('code','=', code[6:8])])
                    codfam = 'rect' if code[1:3] in ('CD','CO','CR','CT','CU','PO','PT','PU') else False
                    if not codfam:
                        codfam = 'othe' if code[1:3] in ('BL','EN','PP','PR','TO','TP','TW') else False
                    if not partner or not fam or not app or not fib or not tit or not gau:
                        is_problem = True
                    else:
                        is_problem = False
                    # Route is no longer pulled from SITPRO; we create the
                    # analysis with the weaving-only placeholder and let the
                    # TEXPLUS pass below assign the real route.
                    base_process_id = self.env['mrp.base.process'].search([
                        ('name', '=', '__SITPRO_PLACEHOLDER__'),
                    ], limit=1)
                    if not base_process_id:
                        base_process_id = self.env['mrp.base.process'].create({
                            'name': '__SITPRO_PLACEHOLDER__',
                            'process_ids': [Command.create({'operation_id': weaving_process.id})],
                        })
                    vals = {
                        'analysis_date': row.fecha,
                        'partner_id': partner.id or False,
                        'product_description': row.descrip.strip(),
                        'product_family_id': fam.id or False,
                        'product_appearance_id': app.id or False,
                        'product_fiber_id': fib.id or False,
                        'product_title_id': tit.id or False,
                        'weave_type': codfam if codfam else ('tubu' if row.tiptej.strip()[:1] == 'T' else 'open'),
                        'gauge_id': gau.id or False,
                        'needles': a_int(row.agujas),
                        'diameter': a_int(row.diametro),
                        'feeders': a_int(row.alimenta),
                        'density': a_int(code[13:16]) if a_int(code[13:16]) else 1,
                        'standard_width': a_float(code[10:13]) if a_float(code[10:13]) else 1,
                        'product_code': code[1:],
                        'is_problem': is_problem,
                        'mrp_base_process_id': base_process_id.id,
                        'sitpro_code': code,
                    }
                    product_analysis = self.create(vals)
                    # Actualizamos el detalle de las rutas desde la base
                    product_analysis._onchange_mrp_base_process_id()
                if not product_analysis.product_id:
                    product_analysis.with_context(by_pass_error=True).action_product()
                ligament = self.env['ligament.type'].search([('name','=',row.ligamento.strip())])
                codhil = row.codigo.strip() if row.codigo.strip() != '0' or row.codigo.strip() != '' else ''
                if last_weaving_data_id and last_weaving_data_id.sitpro_sheet != row.ficha.strip():
                    last_product_analysis.weaving_data_ids = [Command.link(last_weaving_data_id.id)]
                    self.create_technical_sheet(last_weaving_data_id, last_product_analysis, last_row)
                    last_product_analysis.state = 'impo'
                if last_weaving_data_id and last_weaving_data_id.sitpro_sheet == row.ficha.strip():
                    vals = {
                        'fiber_ids': [Command.create({
                            'weight': a_float(row.porcen),
                            'ligament_id': ligament.id or False,
                            'product_template_id': (self.env['product.template'].search([('default_code','=', codhil)]).id or self.env['product.template'].create({'name': row.articulo.strip(), 'default_code': codhil, 'categ_id': self.env.company.thread_category_ids[0].id, 'uom_id': self.env.ref('uom.product_uom_kgm').id}).id) if codhil else False,
                            'line_ids': [Command.create({
                                'length': a_float(row.lm1),
                            })]
                        })]
                    }
                    last_weaving_data_id.write(vals)
                else:
                    vals = {
                        'sitpro_sheet': row.ficha.strip(),
                        'partner_id': partner.id or False,
                        'stylo': row.stylo.strip(),
                        'notes': row.obs,
                        'fiber_ids': [Command.create({
                            'weight': a_float(row.porcen),
                            'ligament_id': ligament.id or False,
                            'product_template_id': (self.env['product.template'].search([('default_code','=', codhil)]).id or self.env['product.template'].create({'name': row.articulo.strip(), 'default_code': codhil, 'categ_id': self.env.company.thread_category_ids[0].id, 'uom_id': self.env.ref('uom.product_uom_kgm').id}).id) if codhil else False,
                            'line_ids': [Command.create({
                                'length': a_float(row.lm1),
                            })]
                        })]
                    }
                    last_weaving_data_id = self.env['analysis.weaving.data'].create(vals)
                    last_row = row
                    last_product_analysis = product_analysis
            if last_weaving_data_id and last_product_analysis and last_row:
                last_product_analysis.weaving_data_ids = [Command.link(last_weaving_data_id.id)]
                self.create_technical_sheet(last_weaving_data_id, last_product_analysis, last_row)
                last_product_analysis.state = 'impo'
        finally:
            try:
                cursor.close()
            except Exception:
                pass
            try:
                conn.close()
            except Exception:
                pass
        # Replace SITPRO routes (or the placeholder created above) with the
        # ones currently in TEXPLUS for every analysis we touched.
        try:
            self._apply_texplus_route_to_analyses(
                self.search([('product_code', '!=', False)])
            )
        except Exception:
            _logger.exception("TEXPLUS route post-sync failed")

    def sync_lab(self):
        def _strip(v):
            return (str(v or '')).strip()

        def _chunked(items, size):
            for start in range(0, len(items), size):
                yield items[start:start + size]

        def _norm(text):
            text = _strip(text).upper()
            if not text:
                return ''
            text = ''.join(ch for ch in unicodedata.normalize('NFD', text) if unicodedata.category(ch) != 'Mn')
            text = re.sub(r'[^A-Z0-9\s]', ' ', text)
            return re.sub(r'\s+', ' ', text).strip()

        def _extract_ld_name(obs_text):
            norm_obs = _norm(obs_text)
            if not norm_obs:
                return False
            match = re.search(r'\bL\s*D\s*[-/ ]?\s*0*(\d{3,7})\b', norm_obs)
            if match:
                return f"LD-{int(match.group(1))}"
            return False

        def _build_partner_index():
            stop = {
                'SAC', 'S A C', 'SA', 'S A', 'SOCIEDAD', 'ANONIMA', 'COMPANIA',
                'CIA', 'EIRL', 'SRL', 'SRL', 'PERU', 'DEL', 'DE', 'LA', 'EL', 'LOS', 'LAS', 'Y'
            }
            partners = self.env['res.partner'].search([('is_company', '=', True)])
            data = []
            for partner in partners:
                nname = _norm(partner.name)
                if not nname:
                    continue
                tokens = [t for t in nname.split() if len(t) > 2 and t not in stop]
                data.append((partner, nname, set(tokens)))
            return data

        def _extract_partner(obs_text, partner_index):
            norm_obs = _norm(obs_text)
            if not norm_obs:
                return False

            alias_map = {
                'WTS': 'WT SOURCING PERU',
            }
            for alias, target in alias_map.items():
                if re.search(rf'\b{re.escape(alias)}\b', norm_obs):
                    target_norm = _norm(target)
                    for partner, pname_norm, _ in partner_index:
                        if target_norm in pname_norm:
                            return partner

            best_partner = False
            best_score = 0
            obs_tokens = set(norm_obs.split())
            for partner, pname_norm, ptokens in partner_index:
                if pname_norm and pname_norm in norm_obs:
                    return partner
                if not ptokens:
                    continue
                overlap = len(ptokens & obs_tokens)
                if overlap > best_score:
                    best_score = overlap
                    best_partner = partner

            return best_partner if best_score >= 2 else False

        def _get_or_create_lab_dev(ld_name, partner, date_value):
            cache_key = ld_name or generic_ld_name
            lab_dev = lab_dev_cache.get(cache_key)
            if lab_dev:
                if partner and not lab_dev.partner_id:
                    lab_dev.partner_id = partner.id
                return lab_dev

            LabDev = self.env['lab.dev']
            lab_dev = LabDev.search([('name', '=', cache_key)], limit=1)
            if not lab_dev and ld_name.startswith('LD-'):
                number = ld_name.split('-', 1)[1]
                lab_dev = LabDev.search([('name', 'ilike', f"LD%{number}")], limit=1)
            if not lab_dev:
                lab_dev = LabDev.create({
                    'name': cache_key,
                    'lab_dev_date': date_value or fields.Date.context_today(self),
                    'partner_id': partner.id if partner else False,
                    'state': 'approved',
                })
            elif partner and not lab_dev.partner_id:
                lab_dev.partner_id = partner.id
            lab_dev_cache[cache_key] = lab_dev
            return lab_dev

        def _texplus_uom(value):
            return {
                1: 'gxl',
                3: 'por',
            }.get(a_int(value), 'gxl')

        def _get_or_create_product(product_code, product_name):
            product_code = _strip(product_code)
            if not product_code:
                return False
            product = product_cache.get(product_code)
            if product is not None:
                return product
            product = self.env['product.template'].search([('default_code', '=', product_code)], limit=1)
            if not product:
                product = self.env['product.template'].create({
                    'name': _strip(product_name) or product_code,
                    'default_code': product_code,
                    'categ_id': self.env.ref('idtx_laboratory.product_categ_3').id,
                    'uom_id': self.env.ref('uom.product_uom_kgm').id,
                    # 'uom_po_id': self.env.ref('uom.product_uom_kgm').id,
                })
            product_cache[product_code] = product
            return product

        def _get_or_create_base_process(process_name):
            process_name = _strip(process_name)
            if not process_name:
                return False
            base_process = base_process_cache.get(process_name)
            if base_process is not None:
                return base_process
            base_process = self.env['base.process'].search([('name', '=', process_name)], limit=1)
            if not base_process:
                base_process = self.env['base.process'].create({'name': process_name})
            base_process_cache[process_name] = base_process
            return base_process

        def _build_texplus_recipe_commands(texplus_recipe):
            if not texplus_recipe:
                return []

            commands = []
            for process_data in texplus_recipe['processes']:
                base_process = _get_or_create_base_process(process_data['process_name'])
                line_commands = []
                for line_data in process_data['lines']:
                    product = _get_or_create_product(line_data['product_code'], line_data['product_name'])
                    line_commands.append(Command.create({
                        'product_id': product.id if product else False,
                        'factor': float(line_data['factor'] or 0.0),
                        'uom': _texplus_uom(line_data['uom_code']),
                    }))

                commands.append(Command.create({
                    'base_process_id': base_process.id if base_process else False,
                    'color_recipe_process_line_ids': line_commands,
                }))
            return commands

        def _load_texplus_recipes(color_code_values):
            if not color_code_values:
                return {}

            recipe_candidates = {}
            texplus_conn = None
            texplus_cursor = None
            try:
                texplus_conn = self._get_texplus_sql_connection()
                texplus_cursor = texplus_conn.cursor()
                sorted_codes = sorted({_strip(code).upper() for code in color_code_values if _strip(code)})

                for chunk in _chunked(sorted_codes, 300):
                    placeholders = ', '.join('?' for _ in chunk)
                    texplus_cursor.execute(
                        f"""
                            SELECT
                                RIGHT('00000000' + LTRIM(RTRIM(f.ForColNom)), 8) AS color_code,
                                f.ForSer,
                                f.ForColNom,
                                f.ForNumCol,
                                f.ForUltMod,
                                f.ForFec,
                                f.ForEst,
                                lf.ProForL,
                                lf.ProForCod,
                                pf.ProForDsc,
                                lp.ProForLin,
                                lp.ProForPrd,
                                lp.ProForDes,
                                lp.ForPrdUMe,
                                lp.ProForCan
                            FROM dbo.CFORMU f
                            LEFT JOIN dbo.LFORMU lf
                                ON lf.EmprCod = f.EmprCod
                               AND lf.ForSer = f.ForSer
                               AND lf.ForColNom = f.ForColNom
                            LEFT JOIN dbo.CPROFO pf
                                ON pf.EmprCod = lf.EmprCod
                               AND pf.ProForCod = lf.ProForCod
                            LEFT JOIN dbo.LPROFO lp
                                ON lp.EmprCod = lf.EmprCod
                               AND lp.ProForCod = lf.ProForCod
                            WHERE f.ForEst = 'S'
                              AND RIGHT('00000000' + LTRIM(RTRIM(f.ForColNom)), 8) IN ({placeholders})
                            ORDER BY color_code, f.ForUltMod DESC, f.ForFec DESC, lf.ProForL, lp.ProForLin
                        """,
                        *chunk,
                    )

                    columns = [col[0].lower() for col in texplus_cursor.description]
                    for raw_row in texplus_cursor.fetchall():
                        row = dict(zip(columns, raw_row))
                        color_code = _strip(row.get('color_code')).upper()
                        if not color_code:
                            continue

                        formula_key = (
                            _strip(row.get('forser')),
                            a_int(row.get('forcolnum')) or 0,
                            a_int(row.get('fornumcol')) or 0,
                        )
                        formulas_for_color = recipe_candidates.setdefault(color_code, {})
                        formula = formulas_for_color.setdefault(formula_key, {
                            'sort_key': (
                                row.get('forultmod') or fields.Datetime.to_datetime('1900-01-01 00:00:00'),
                                row.get('forfec') or fields.Datetime.to_datetime('1900-01-01 00:00:00'),
                                formula_key,
                            ),
                            'process_map': {},
                        })

                        process_code = _strip(row.get('proforcod'))
                        process_name = _strip(row.get('profordsc')) or process_code
                        process_order = a_int(row.get('proforl')) or 0
                        if not process_name:
                            continue

                        process_entry = formula['process_map'].setdefault((process_order, process_code, process_name), {
                            'process_name': process_name,
                            'order': process_order,
                            'line_map': {},
                        })

                        product_code = _strip(row.get('proforprd'))
                        product_name = _strip(row.get('profordes')) or product_code
                        product_order = a_int(row.get('proforlin')) or 0
                        if product_code or product_name:
                            process_entry['line_map'][(product_order, product_code, product_name)] = {
                                'product_code': product_code,
                                'product_name': product_name,
                                'factor': row.get('proforcan') or 0.0,
                                'uom_code': row.get('forprdume'),
                                'order': product_order,
                            }
            finally:
                try:
                    texplus_cursor.close()
                except Exception:
                    pass
                try:
                    texplus_conn.close()
                except Exception:
                    pass

            selected_recipes = {}
            for color_code, formulas in recipe_candidates.items():
                if not formulas:
                    continue
                selected_formula = max(formulas.values(), key=lambda item: item['sort_key'])
                processes = []
                for _, process_data in sorted(selected_formula['process_map'].items(), key=lambda item: item[0]):
                    lines = [
                        line_data
                        for _, line_data in sorted(process_data['line_map'].items(), key=lambda item: item[0])
                    ]
                    processes.append({
                        'process_name': process_data['process_name'],
                        'order': process_data['order'],
                        'lines': lines,
                    })
                selected_recipes[color_code] = {
                    'processes': processes,
                }
            return selected_recipes

        try:
            conn = self._get_sql_connection()
            cursor = conn.cursor()
            # query = f"""
            #     SELECT
            #         l.gt,
            #         l.cb,
            #         l.ints,
            #         l.corr,
            #         l.descrip,
            #         l.obs
            #     FROM lab_colores02 l
            #     where l.gt is NOT NULL 
            #     AND l.cb is not null 
            #     AND l.ints is not null 
            #     AND l.corr is not null 
            #     and LTRIM(RTRIM(l.gt)) <> ''
            #     and LTRIM(RTRIM(l.cb)) <> ''
            #     and LTRIM(RTRIM(l.ints)) <> ''
            #     and LTRIM(RTRIM(l.corr)) <> '';
            # """
            
            query = f"""
                    SELECT
                        lc.gt,
                        lc.cb,
                        lc.ints,
                        lc.corr,
                        lc.descrip,
                        lc.obs,
                        vl.cdgart
                    FROM lab_colores02 lc
                    CROSS APPLY (
                        SELECT TOP 1 vl2.cdgart
                        FROM vta_det_pedido vl2
                        WHERE vl2.cdgcol =
                            LTRIM(RTRIM(ISNULL(lc.gt,''))) +
                            LTRIM(RTRIM(ISNULL(lc.cb,''))) +
                            LTRIM(RTRIM(ISNULL(lc.ints,''))) +
                            RIGHT('0000' + CAST(CAST(lc.corr AS INT) AS VARCHAR(10)), 4)
                        AND LTRIM(RTRIM(vl2.cdgart)) <> ''
                    ) vl
                    WHERE lc.gt IS NOT NULL
                    AND lc.cb IS NOT NULL
                    AND lc.ints IS NOT NULL
                    AND lc.corr IS NOT NULL
                    AND LTRIM(RTRIM(lc.gt)) <> ''
                    AND LTRIM(RTRIM(lc.cb)) <> ''
                    AND LTRIM(RTRIM(lc.ints)) <> ''
                    AND LTRIM(RTRIM(lc.corr)) <> '';
            """
            cursor.execute(query)
            columns = [col[0].lower() for col in cursor.description]
            cursor_result = [dict(zip(columns, row)) for row in cursor.fetchall()]
            company_partner = self.env.company.partner_id
            partner_index = _build_partner_index()
            generic_ld_name = 'LD-GENERICA'
            lab_dev_cache = {}
            product_cache = {}
            base_process_cache = {}

            prepared_rows = []
            process_codes = set()
            range_codes = set()
            intensity_codes = set()
            color_codes = set()
            for row in cursor_result:
                gt = _strip(row.get('gt'))
                cb = _strip(row.get('cb'))
                ints = _strip(row.get('ints'))
                corr_raw = _strip(row.get('corr'))
                obs = _strip(row.get('obs'))
                desc = _strip(row.get('descrip'))
                cdgart = _strip(row.get('cdgart'))

                if not (gt and cb and ints and corr_raw):
                    continue

                corr = str(a_int(corr_raw)).zfill(4) if a_int(corr_raw) else corr_raw.zfill(4)
                color_code = f"{gt}{cb}{ints}{corr}"
                prepared_rows.append({
                    'gt': gt,
                    'cb': cb,
                    'ints': ints,
                    'obs': obs,
                    'desc': desc,
                    'color_code': color_code,
                    'cdgart': cdgart
                })
                process_codes.add(gt)
                range_codes.add(cb)
                intensity_codes.add(ints)
                color_codes.add(color_code)

            total = len(prepared_rows)
            if not total:
                return

            process_map = {
                record.code: record
                for record in self.env['color.process.type'].search([('code', 'in', list(process_codes))])
            }
            color_range_map = {
                record.code: record
                for record in self.env['color.range'].search([('code', 'in', list(range_codes))])
            }
            intensity_map = {
                record.code: record
                for record in self.env['color.intensity'].search([('code', 'in', list(intensity_codes))])
            }

            existing_lines_by_code = {}
            for line in self.env['lab.dev.line'].search([('color_code', 'in', list(color_codes))]):
                code_key = _strip(line.color_code).upper()
                current = existing_lines_by_code.get(code_key)
                if not current or (line.color_recipe_ids and not current.color_recipe_ids):
                    existing_lines_by_code[code_key] = line

            target_color_codes = set()
            for row in prepared_rows:
                color_code = row['color_code'].upper()
                existing_line = existing_lines_by_code.get(color_code)
                if not existing_line:
                    target_color_codes.add(color_code)
                    continue
                if not existing_line.color_recipe_ids:
                    target_color_codes.add(color_code)
                    continue
                if not existing_line.color_recipe_ids.filtered('color_recipe_process_ids'):
                    target_color_codes.add(color_code)

            texplus_recipes_by_color = _load_texplus_recipes(target_color_codes)

            skipped_existing_recipe = 0
            progress_every = max(1000, total // 20)

            for contador, row in enumerate(prepared_rows, 1):
                if contador == 1 or contador % progress_every == 0 or contador == total:
                    _logger.info("sync_lab %s / %s  %s%%", contador, total, int((contador / total) * 100))
                gt = row['gt']
                cb = row['cb']
                ints = row['ints']
                obs = row['obs']
                desc = row['desc']
                color_code = row['color_code']
                cdgart = row['cdgart'][1:]

                existing_line = existing_lines_by_code.get(color_code.upper())
                if existing_line and existing_line.color_recipe_ids.filtered('color_recipe_process_ids'):
                    skipped_existing_recipe += 1
                    continue

                process = process_map.get(gt)
                color_range = color_range_map.get(cb)
                intens_obj = intensity_map.get(ints)
                texplus_recipe = texplus_recipes_by_color.get(color_code.upper())
                recipe_commands = _build_texplus_recipe_commands(texplus_recipe)

                partner = _extract_partner(obs, partner_index) or company_partner
                ld_name = _extract_ld_name(obs) or generic_ld_name
                product = self.env['product.template'].search([('default_code', '=', cdgart)], limit=1)
                
                if existing_line:
                    recipe = existing_line.color_recipe_ids.filtered(lambda rec: not rec.color_recipe_process_ids)[:1]
                    existing_line.write({
                        'product_id': product.id if product else False,
                    })
                    if not recipe and not existing_line.color_recipe_ids:
                        existing_line.color_recipe_ids = [Command.create({
                            'state': 'approved',
                            'color_recipe_process_ids': recipe_commands,
                        })]
                    elif recipe and recipe_commands:
                        recipe.write({
                            'color_recipe_process_ids': [Command.clear(), *recipe_commands],
                        })
                else:
                    lab_dev = _get_or_create_lab_dev(ld_name, partner, fields.Date.context_today(self))
                    new_line = self.env['lab.dev.line'].create({
                        'lab_dev_id': lab_dev.id,
                        'product_id': product.id if product else False,
                        'color_name': desc or color_code,
                        'color_code': color_code,
                        'color_process_type_id': process.id if process else False,
                        'color_range_id': color_range.id if color_range else False,
                        'color_intensity_id': intens_obj.id if intens_obj else False,
                        'color_recipe_ids': [Command.create({
                            'state': 'approved',
                            'color_recipe_process_ids': recipe_commands,
                        })],
                        'state': 'approved',
                    })
                    existing_lines_by_code[color_code.upper()] = new_line
            if skipped_existing_recipe:
                _logger.info("sync_lab omitio %s registros porque la receta ya existia", skipped_existing_recipe)
        finally:
            try:
                cursor.close()
            except Exception:
                pass
            try:
                conn.close()
            except Exception:
                pass

    def create_technical_sheet(self, lw, pa, row):
        route_line_ids = []
        for route in pa.routing_ids.sorted(key=lambda r: r.sequence):
            line_parameter_ids = []
            for item in TABLES:
                if route.operation_id.name in item['process']:
                    table = item['table']
                    cursor_param = self.get_parameters_data(row.ficha.strip(), table)
                    for row_param in cursor_param:
                        for field_name, field_value in row_param.items():
                            value = field_value.strip() if isinstance(field_value, str) else field_value
                            if field_name in FIELD_NAMES and value and value is not None:
                                line_parameter_ids.append(
                                    Command.create({
                                        'name': FIELD_NAMES[field_name],
                                        'value': value,
                                        'is_observation': field_name == 'obs',
                                    })
                                )
            route_line_ids.append(Command.create({
                'operation_id': route.operation_id.id,
                'line_parameter_ids': line_parameter_ids
            }))
        if line_parameter_ids:
            x = 1
        # Ficha Tecnica
        lw.technical_sheet_id = self.env['technical.sheet'].create({
            'sitpro_sheet': row.ficha.strip(),
            'analysis_id': pa.id,
            'product_code': pa.product_code,
            'product_id': pa.product_id.id,
            'partner_id': lw.partner_id.id,
            'notes': row.obs,
            'fabric_composition': '\n'.join([
                f'{round(f.percentage * 100)}% {f.product_template_id.name}'
                for f in lw.fiber_ids if f.product_template_id
            ]).strip(),
            'density': pa.density,
            'width': pa.standard_width,
            'gauge_id': pa.gauge_id.id,
            'stylo': lw.stylo,
            'route_line_ids': route_line_ids,
            # Datos de crudo
            'raw_width': a_float(row.ancho),
            'raw_density': a_float(row.densidad),
            'raw_widening': a_float(row.ensanch),
            # Datos de acabado
            'finish_width': a_float(row.trollo),
            'finish_density': a_float(row.vrollo),
            'finish_yield': a_float(row.rrollo),
        })
        lw.technical_sheet_id.action_done()
    
class AnalysisWeavingData(models.Model):
    _inherit = 'analysis.weaving.data'

    sitpro_sheet = fields.Char('Sitpro Sheet', copy=False)


class ColorRecipe(models.Model):
    _inherit = 'color.recipe'

    def sync_lab_recipes_from_texplus(self):
        analysis_model = self.env['product.analysis']
        product_cache = {}
        base_process_cache = {}
        selected_recipes = self.filtered(lambda recipe: recipe.lab_dev_line_id and recipe.color_code)
        color_codes = {str(recipe.color_code or '').strip().upper() for recipe in selected_recipes if str(recipe.color_code or '').strip()}
        texplus_recipes_by_color = analysis_model._load_texplus_recipes_by_color(color_codes)

        updated_recipes = 0
        missing_texplus = 0
        skipped_with_recipe = 0

        for recipe in selected_recipes:
            if recipe.color_recipe_process_ids:
                skipped_with_recipe += 1
                continue

            color_code = str(recipe.color_code or '').strip().upper()
            texplus_recipe = texplus_recipes_by_color.get(color_code)
            if not texplus_recipe:
                missing_texplus += 1
                continue

            recipe_commands = analysis_model._build_texplus_recipe_commands(
                texplus_recipe,
                product_cache,
                base_process_cache,
            )
            if not recipe_commands:
                missing_texplus += 1
                continue

            recipe.write({
                'color_recipe_process_ids': [Command.clear(), *recipe_commands],
            })
            updated_recipes += 1

        message = (
            f"Recetas TEXPLUS seleccionadas: actualizadas={updated_recipes}, "
            f"sin_formula={missing_texplus}, "
            f"omitidas_con_procesos={skipped_with_recipe}"
        )
        _logger.info(message)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('TEXPLUS'),
                'message': message,
                'type': 'success',
                'sticky': False,
            }
        }

class TechnicalSheet(models.Model):
    _inherit = 'technical.sheet'

    sitpro_sheet = fields.Char('Sitpro Sheet', copy=False)