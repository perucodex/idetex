# -*- coding: utf-8 -*-
import re
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
                WHERE tcr.fecha >= '2020-01-01'
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
                    base_process_id = self.env['mrp.base.process'].search([('name','=', row.fascod.strip())])
                    if not base_process_id:
                        ruta_cursor = self.get_routing_data(row.fascod.strip())
                        base_process_id = self.env['mrp.base.process'].create({'name': row.fascod.strip(),'process_ids': [Command.create({'operation_id': weaving_process.id})]})
                        base_process_id.write({
                            'process_ids': [Command.create({
                                'operation_id': self.env['mrp.routing.workcenter.operation'].search([('name','=', rrow.FasDsc.strip())]).id or self.env['mrp.routing.workcenter.operation'].create({'name': rrow.FasDsc.strip(), 'workcenter_id': self.env['mrp.workcenter'].search([('name','=', str(rrow.area).strip().upper())]).id or self.env['mrp.workcenter'].create({'name': str(rrow.area).strip().upper()}).id}).id,
                            }) for rrow in ruta_cursor]
                        })
                        weaving_lines = base_process_id.process_ids.filtered(lambda l: l.operation_id.operation_type == 'weaving')
                        # Si no hay tejido creamos uno sino eliminamos hasta que quede el primero
                        if weaving_lines:
                            weaving_line = weaving_lines[0]
                            if len(weaving_lines) > 1:
                                (weaving_lines - weaving_line).unlink()
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
                        'density': a_int(code[10:13]) if a_int(code[10:13]) else 1,
                        'standard_width': a_float(code[13:16]) if a_float(code[13:16]) else 1,
                        'product_code': code[1:],
                        'is_problem': is_problem,
                        'mrp_base_process_id': base_process_id.id,
                        'sitpro_code': code,
                    }
                    product_analysis = self.create(vals)
                    # Actualizamos el detalle de las rutas desde la base
                    product_analysis._onchange_mrp_base_process_id()
                if not product_analysis.product_id:
                    product_analysis.action_product()
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

    def sync_lab(self):
        try:
            conn = self._get_sql_connection()
            cursor = conn.cursor()
            query = f"""
                SELECT
                    v.fecha,
                    v.lab,
                    c.ruc,
                    v.cdgart,
                    v.cdgcolor,
                    v.descolor,
                    v.obs,
                    l.gt,
                    l.cb,
                    l.ints,
                    L.corr
                FROM vta_labs v
                INNER JOIN lab_colores02 l
                    ON LTRIM(RTRIM(v.cdgcolor)) =
                    LTRIM(RTRIM(ISNULL(l.gt,''))) +
                    LTRIM(RTRIM(ISNULL(l.cb,''))) +
                    LTRIM(RTRIM(ISNULL(l.ints,''))) +
                    RIGHT('0000' + CAST(CAST(l.corr AS INT) AS VARCHAR(10)), 4)
                INNER JOIN clientes c ON c.cdgclie = v.cdgclien
                where l.gt is NOT NULL 
                AND l.cb is not null 
                AND l.ints is not null 
                AND l.corr is not null 
                and LTRIM(RTRIM(l.gt)) <> ''
                and LTRIM(RTRIM(l.cb)) <> ''
                and LTRIM(RTRIM(l.ints)) <> ''
                and LTRIM(RTRIM(l.corr)) <> '';
            """
            cursor.execute(query)
            cursor_result = cursor.fetchall()
            total = len(cursor_result)
            for contador, row in enumerate(cursor_result, 1):
                _logger.info(str(contador) + ' / ' + str(total) + '  ' + str(int((contador / total)*100)) + '%')
                partner = self.env['res.partner'].search([('vat','=', row.ruc.strip()),('is_company','=', True)])
                codigo = row.cdgart[1:].strip()
                product = self.env['product.template'].search([('default_code','=', codigo)])
                if not partner or not product:
                    continue
                process = self.env['color.process.type'].search([('code','=',row.gt.strip())])
                range = self.env['color.range'].search([('code','=',row.cb.strip())])
                intens = self.env['color.intensity'].search([('code','=',row.ints.strip())])
                lab_dev_id = self.env['lab.dev'].search([('name','=', row.lab.strip())])
                color_code = row.gt.strip() + row.cb.strip() + row.ints.strip() + row.corr.strip().zfill(4)
                if lab_dev_id:
                    vals = {
                        'lab_dev_line_ids': [Command.create({
                            'product_id': product.id or False,
                            'color_name': row.descolor.strip(),
                            'color_code': color_code,
                            'color_process_type_id': process.id,
                            'color_range_id': range.id,
                            'color_intensity_id': intens.id,
                            'state': 'approved',
                        })],
                    }
                    lab_dev_id.write(vals)
                else:
                    vals = {
                        'lab_dev_date': row.fecha,
                        'name': row.lab.strip(),
                        'partner_id': partner.id or False,
                        'lab_dev_line_ids': [Command.create({
                            'product_id': product.id or False,
                            'color_name': row.descolor.strip(),
                            'color_code': color_code,
                            'color_process_type_id': process.id,
                            'color_range_id': range.id,
                            'color_intensity_id': intens.id,
                            'state': 'approved',
                        })],
                        'state': 'approved',
                    }
                    lab_dev_id.create(vals)
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

    sitpro_sheet = fields.Char('Sitpro Sheet')

class TechnicalSheet(models.Model):
    _inherit = 'technical.sheet'

    sitpro_sheet = fields.Char('Sitpro Sheet')