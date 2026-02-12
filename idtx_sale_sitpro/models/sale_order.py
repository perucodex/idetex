import dbf
import pyodbc
import re
import logging
from odoo import models, api, fields, _
from odoo.exceptions import UserError
from dateutil.relativedelta import relativedelta

_logger = logging.getLogger(__name__)

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    telefono = fields.Selection([('FIJO', 'Fijo'),('CELULAR', 'Celular'),], string='Teléfono')
    grem = fields.Char('Guia de Remisión del Cliente')
    occ = fields.Char('Orde de Compra del Cliente')
    fecoc = fields.Date('Fecha de Orden de Compra', default=lambda self: fields.Date.context_today(self))
    almacen = fields.Selection([
        ('TELA ACABADA', 'Tela Acabada'),
        ('HILOS', 'Hilos'),
        ('RESIDUOS', 'Residuos'),
    ], string='Almacen')
    tipdesp = fields.Selection([
        ('PARCIAL', 'Parcial'),
        ('TODO JUNTO', 'Todo Junto'),
    ], string='Tipo de Despacho')
    fechadespacho = fields.Datetime('Fecha de Despacho', default=lambda self: fields.Datetime.to_datetime(fields.Date.context_today(self) + relativedelta(days=30)))
    sitpro_sale_type_id = fields.Many2one('sitpro.sale.type', string='Sitpro Sale Type')
    sale_domain = fields.Char(compute='_compute_sale_domain', store=True)

    def action_confirm(self):
        res = super().action_confirm()

        for order in self:
            if not order.user_id.vendor_code_sitpro:
                raise UserError(_('Salesman %s does not have a vendor code for SitPro') % order.user_id.name)
            if not self.payment_term_id.sitpro_code:
                raise UserError(_('Payment Term %s does not have a SitPro code') % self.payment_term_id.name)
            if not order.company_id.is_company_produce or order.is_quote:
                continue

            try:
                order._export_to_foxpro()
                order.message_post(
                    body=_('✅ Pedido exportado exitosamente a SitPro'))
            except Exception as e:
                _logger.exception('Error exportando pedido %s a SitPro', order.name)
                order.message_post(
                    body=_(
                        '⚠ Error exportando el pedido a SitPro:<br/>%s'
                    ) % str(e)
                )

        return res
    
    @api.depends('sale_type')
    def _compute_sale_domain(self):
        for rec in self:
            if rec.sale_type == 'sale':
                rec.sale_domain = 'V'
            else:
                rec.sale_domain = 'S'

    # ------------------------------------------------------------------
    # Buscar cliente en DBF FoxPro indexado
    # ------------------------------------------------------------------

    def find_cliente_codigo(self, filename, vat_cliente):
        table = None
        try:
            table = dbf.Table(filename, codepage='cp1252')
            with table:
                key = (vat_cliente or '').strip()
                idx = table.create_index(lambda r: (r.RUC.strip(),))
                matches = idx.search(match=(key,), partial=False)
                for rec in matches:
                    if not dbf.is_deleted(rec):
                        return rec.CDGCLIE, False
                next_code = self._siguiente_codigo_por_letra(table, self.partner_id.name[:1])
                return next_code, True
        finally:
            if table:
                table.close()

    def _siguiente_codigo_por_letra(self, table, letra):
        patron = re.compile(rf'^{re.escape(letra)}(\d{{4}})$')
        max_n = 0
        for rec in table:
            if dbf.is_deleted(rec):
                continue
            cdg = (getattr(rec, 'CDGCLIE', '') or '').strip().upper()
            m = patron.match(cdg)
            if m:
                n = int(m.group(1))
                if n > max_n:
                    max_n = n
        siguiente = max_n + 1
        if siguiente > 9999:
            raise ValueError(f'Se agotó el correlativo para la letra {letra} (>{letra}9999).')
        return f'{letra}{siguiente:04d}'
    
    # ------------------------------------------------------------------
    # Exportación FoxPro
    # ------------------------------------------------------------------

    def _export_to_foxpro(self):
        self.ensure_one()
        
        file_cab = '/mnt/fox/sit06/JP_DBF/vta_cab_pedido.dbf'
        file_det = '/mnt/fox/sit06/JP_DBF/vta_det_pedido.dbf'
        clientes_dbf = '/mnt/fox/sit06/JP_DBF/clientes.dbf'

        # --------------------
        # Cabecera
        # --------------------
        codcli, nuevo = self.find_cliente_codigo(clientes_dbf,self.partner_id.vat)
        if nuevo:
            # Inserta en dbf
            cli_values = {
                'CDGCLIE': str(codcli).strip()[:10],
                'RAZSOC': self.partner_id.name or '',
                'RUC': self.partner_id.vat or '',
                'DIRECCI': self.partner_id.street or '',
                'PAIS': self.partner_id.country_id.name or '',
                'DESDIS': self.partner_id.l10n_pe_district.name or '',
                'DPTO': self.partner_id.state_id.name or '',
                'EMAIL': self.partner_id.email or '',
            }
            self._insert_dbf_record(clientes_dbf, cli_values)
            cli_values.update({
                'CONTACTOVT': self.user_id.vendor_code_sitpro or '',
                'TELEF1': self.partner_id.phone or '',
                'OBSCLIEN': '',
                'EMAILS': self.partner_id.email or '',
            })
            self._insert_sql_record(cli_values)

        for tax_totals in self.tax_totals['subtotals']:
            for tax in tax_totals['tax_groups']:
                if tax['group_name'] == 'IGV':
                    total_tax = tax['tax_amount_currency']
        orden = dbf.Char((self.name or '').strip())
        orden = str(orden or '')[:10].ljust(10)
        cab_values = {
            'NUMORDPED': orden[:10],
            'FECHA': self.date_order.date(),
            'CDGCLIE': str(codcli).strip()[:10],
            'CDGTIPVEN': self.payment_term_id.sitpro_code,
            'CDGTIPMER': '001' if self.fiscal_position_id.name == 'LOCAL PERÚ' else '002',
            'LAB': (self.lab_dev_ids[0].name or '')[:10] if self.lab_dev_ids else '',
            'CONDPAGO': (self.payment_term_id.name or '')[:150], # Traer tabla
            'CDGVEN': self.user_id.vendor_code_sitpro or '', # Crear campo oculto en vendedor para ingresar codigo de sitpro
            'TELEFONO': self.telefono, # Selection 1
            'GREM': (self.grem or '')[:10], #Char
            'OCC': (self.occ or '')[:30], #Char
            'TOTKIL': sum(self.order_line.filtered(lambda l: l.product_id.is_weaving).mapped('product_uom_qty')), # Total de kilos
            'SUBTOTAL': self.amount_untaxed, # Sub Total 
            'CANIGV': total_tax, # Total IGV
            'TOTNET': float(self.amount_total),
            'TJ': dbf.Logical(True),
            'TN': dbf.Logical(False),
            'ACTIVO': dbf.Logical(True),
            'DSTOCK': dbf.Logical(True if self.almacen else False),
            'ALMACEN': (self.almacen or '')[:20],
            'TIPDESP': (self.tipdesp or '')[:30],
            'RAZSOC': (self.partner_id.name or '')[:100],
            'MONEDA': 'D' if self.currency_id.name == 'USD' else 'S', 
            'IDTIPO': (self.sitpro_sale_type_id.code or '')[:10],
            'TIPOVENTA': (self.sitpro_sale_type_id.name or '')[:100],
            'ORDEN': (self.sitpro_sale_type_id.orden or '')[:1],
            'UM1': 'KG',
            'FECHADESPA': self.fechadespacho,
            'FECOC': self.fecoc,
            'EMPRESA': (self.env.company.name or '')[:50],
            'USUARIO': self.env.user.name,
        }

        self._insert_dbf_record(file_cab, cab_values)

        # --------------------
        # Detalle
        # --------------------
        for item, line in enumerate(self.order_line.filtered(lambda l: l.product_id.is_weaving), 1):

            det_values = {
                'NUMORDPED': orden[:10],
                'ITEM': item,
                'CDGART': line.product_id.analysis_is.sitpro_code or line.product_id.default_code or '',
                'DESCRIP': line.product_id.name or '',
                'CDGCOL': (line.lab_dev_line_id.color_code or '0XDS0001') if line.color_name else '',
                'DESCOL': line.lab_dev_line_id.color_name or '',
                'ANCHO': (line.bom_id.technical_sheet_id.width / 100),
                'DENSIDAD': line.bom_id.technical_sheet_id.density,
                'TIPTEJ': 'ABIERTO' if line.bom_id.technical_sheet_id.weave_type == 'open' else 'TUBULAR', # abierto o tubular
                'KILO': float(line.product_uom_qty),
                'METROS': float(line.product_uom_qty * line.bom_id.technical_sheet_id.yield_meter),
                # 'PESCL': float(line.pescl),
                'PREUNI': float(line.price_unit),
                'IMPORTE': float(line.price_subtotal), # sin igv
                'UNID': float(0), # Rectilineos
                'TALLAS': '', # Rectilineos
                'PROCOD': line.bom_id.technical_sheet_id.mrp_base_process_id.name,
                'RUTA': (';'.join(l.operation_id.name for l in line.bom_id.technical_sheet_id.route_line_ids.filtered(lambda o: o.operation_id.unit_price > 0 or o.operation_id.type_prices == 'col' and sum(o.operation_id.product_color_price_ids.mapped('unit_price')) > 0).sorted(key=lambda r: r.sequence)))[:180],
            }

            self._insert_dbf_record(file_det, det_values)

    # ------------------------------------------------------------------
    # Inserción segura DBF
    # ------------------------------------------------------------------

    @api.model
    def _insert_dbf_record(self, filename, values):
        table = None
        try:
            table = dbf.VfpTable(filename, codepage='cp1252')
            table.open(mode=dbf.READ_WRITE)
            record = {k.upper(): v for k, v in values.items()}
            for field in record:
                if field not in table.field_names:
                    raise Exception(f"Campo '{field}' no existe en {filename}")
            table.append(record)
        finally:
            if table:
                table.close()

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
    
    def _insert_sql_record(self, cli_values):
        conn = None
        cursor = None
        try:
            conn = self._get_sql_connection()
            cursor = conn.cursor()
            query = """
                INSERT INTO clientes
                (CDGCLIE, RAZSOC, RUC, DIRECCI, PAIS, DESDIS, DPTO, EMAIL, CONTACTOVT, TELEF1, OBSCLIEN, EMAILS)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """
            params = (
                cli_values['CDGCLIE'].upper(),
                cli_values['RAZSOC'].upper(),
                cli_values['RUC'].upper(),
                cli_values['DIRECCI'].upper(),
                cli_values['PAIS'].upper(),
                cli_values['DESDIS'].upper(),
                cli_values['DPTO'].upper(),
                cli_values['EMAIL'].upper(),
                cli_values['CONTACTOVT'].upper(),
                cli_values['TELEF1'].upper(),
                cli_values['OBSCLIEN'].upper(),
                cli_values['EMAILS'].upper(),
            )
            cursor.execute(query, params)
            conn.commit()
        finally:
            try:
                if cursor:
                    cursor.close()
            except Exception:
                pass
            try:
                if conn:
                    conn.close()
            except Exception:
                pass