from odoo import models, fields, api, _
from odoo.fields import Command
from odoo.exceptions import UserError, RedirectWarning
from datetime import datetime, timedelta
import base64
import re
import requests
import zipfile
import io
import calendar

# import subprocess
# import sys
# def install(package):
# 	subprocess.check_call([sys.executable, "-m", "pip", "install", package])
# try:
# 	import tuspy
# except:
# 	install('tuspy==1.0.3')
# try:
# 	import tusclient
# except:
#     install('tusclient==0.2.1')

# import tuspy
import tusclient

class SireSunat(models.Model):
    _name = 'sire.sunat'
    _inherit = 'mail.thread'
    _description = 'Sire Sunat'

    name = fields.Char('Name', compute='_compute_name')
    period = fields.Date('Period', tracking=True)
    proposal_line_ids = fields.One2many('proposal.line', 'sire_sunat_id', string='Documents', copy=False, tracking=True)
    total = fields.Float('Total', compute='_compute_total_proposal', copy=False)
    proposal_ticket_number = fields.Char('Proposal Ticket Number', copy=False)
    proposal_ticket_date = fields.Datetime('Proposal Ticket Date', copy=False)
    proposal_zip_file = fields.Binary(string="Proposal ZIP File", readonly=True)
    preliminary_ticket_number = fields.Char('Preliminary Ticket Number', copy=False)
    preliminary_ticket_date = fields.Datetime('Preliminary Ticket Date', copy=False)
    preliminary_zip_file = fields.Binary(string="Preliminary ZIP File", readonly=True)
    sire_type = fields.Char('Sire Type')
    account_move_ids = fields.Many2many('account.move', string='Invoices', copy=False, tracking=True)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('proposal', 'Proposal'),
        ('check', 'Checked'),
        ('preliminary', 'Preliminary'),
        ('register', 'Registered'),
    ], string='State', default='draft', tracking=True)
    company_id = fields.Many2one('res.company', 'Compañia', default=lambda self: self.env.company)

    # @api.constrains('account_move_ids')
    # def _check_account_move_ids(self):
    #     if len(self.account_move_ids.ids) > 1:
    #         raise UserError(_('No se debe de seleccionar registros'))

    @api.model_create_multi
    def create(self, vals_list):
        for val in vals_list:
            val['sire_type'] = self.env.context.get('default_sire_type')
        return super().create(vals_list)

    @api.depends('period')
    def _compute_name(self):
        for rec in self:
            if rec.period:
                rec.name = ('Purchase ' if rec.sire_type == 'p' else 'Sale ') + calendar.month_name[rec.period.month].capitalize() + ' ' + str(rec.period.year)
            else:
                rec.name = ('Purchase ' if rec.sire_type == 'p' else 'Sale ')

    def _compute_total_proposal(self):
        for rec in self:
            if rec.proposal_line_ids:
                rec.total = sum(rec.proposal_line_ids.mapped('total'))
            else:
                rec.total = 0

    @api.onchange('period')
    def _onchange_period(self):
        self.proposal_ticket_number = ''

    def _get_headers(self, token):
        return {
            'Authorization': 'Bearer ' + token,
            'Accept': 'application/json',
            'Content-Type': 'application/json'
        }

    def _get_token(self):
        if not self.company_id.partner_id.vat:
            raise RedirectWarning(
                _('Company does not have a VAT number'),
                self.env.ref('base.action_res_company_form').id,
                _("Go to Company"),
                )
        if not self.company_id.client_id or not self.company_id.client_secret or not self.company_id.l10n_pe_edi_provider_username or not self.company_id.l10n_pe_edi_provider_password:
            raise RedirectWarning(
                _('Some configuration is missing for Sire SUNAT'),
                self.env.ref('account.action_account_config').id,
                _("Go to the configuration panel"),
                )
        try:
            if self.company_id.l10n_pe_edi_provider == 'sunat':
                username = str(self.company_id.l10n_pe_edi_provider_username)
            else:
                username = str(self.company_id.partner_id.vat) + str(self.company_id.l10n_pe_edi_provider_username)
            client_id = self.company_id.client_id
            client_secret = self.company_id.client_secret 
            # username = str(self.company_id.partner_id.vat) + str(self.company_id.l10n_pe_edi_provider_username)
            password = self.company_id.l10n_pe_edi_provider_password 
            payload = {
                'grant_type': 'password',
                'scope': 'https://api-sire.sunat.gob.pe',
                'client_id': client_id,
                'client_secret': client_secret,
                'username': username,
                'password': password
            }
            token_url = f"https://api-seguridad.sunat.gob.pe/v1/clientessol/{client_id}/oauth2/token/"
            response = requests.post(token_url, data=payload)
            if response.status_code == 200:
                return response.json().get('access_token')
            else:
                # Simula "ir al except" lanzando una excepción manualmente con el mensaje
                try:
                    error_msg = response.json().get('error_description') or response.text
                except Exception:
                    error_msg = response.text
                raise Exception(_("SUNAT Authentication failed: %s") % error_msg)

        except Exception as e:
            raise UserError(_(str(e)))
        
    def get_ticket_info(self, period, headers, ticket):
        while True:
            try:
                ticket_url = f"https://api-sire.sunat.gob.pe/v1/contribuyente/migeigv/libros/rvierce/gestionprocesosmasivos/web/masivo/consultaestadotickets?perIni={period}&perFin={period}&page=1&perPage=20&numTicket={ticket}"
                ticket_response = requests.get(ticket_url, headers=headers)
                json_data = ticket_response.json()
                if ticket_response.status_code == 200:
                    desEstadoProceso = json_data.get('registros')[0]['desEstadoProceso']
                    if desEstadoProceso == 'Terminado':
                        break                    
                else:
                    raise UserError(ticket_response.text)
            except Exception as e:
                raise UserError(e)
        return ticket_response
    
    def get_zip_file(self, file_name, codTipoAchivoReporte,period, headers):
        file_url = f"https://api-sire.sunat.gob.pe/v1/contribuyente/migeigv/libros/rvierce/gestionprocesosmasivos/web/masivo/archivoreporte?nomArchivoReporte={file_name}&codTipoArchivoReporte={codTipoAchivoReporte}&codLibro=140000&perTributario={period}&codProceso=10&numTicket={self.proposal_ticket_number}"
        zip_file = requests.get(file_url, headers=headers)
        if zip_file.status_code != 200:
            raise UserError(zip_file.text)
        else:
            # Crear un objeto de BytesIO para mantener el contenido en memoria
            memory_zip_file = io.BytesIO()
            # Descomprimir el contenido y escribirlo en el objeto BytesIO
            with zipfile.ZipFile(io.BytesIO(zip_file.content), 'r') as zip_ref:
                for file_info in zip_ref.infolist():
                    # Leer cada archivo en el ZIP y escribirlo en la memoria
                    file_content = zip_ref.read(file_info.filename)
                    memory_zip_file.write(file_content)

            # Cambiar la posición del objeto BytesIO al principio
            memory_zip_file.seek(0)
            # Guardar el contenido del archivo ZIP en el campo binario
            self.write({'proposal_zip_file': base64.b64encode(memory_zip_file.read())})

        return zip_file

    def unzip_file_create_lines(self, zip_file):
        # Descomprimir, leer propuesta y crear lineas
        with zipfile.ZipFile(io.BytesIO(zip_file), 'r') as zip_ref:
            # Obtén la lista de nombres de archivos en el ZIP (debería haber solo uno en este caso)
            txt_file = zip_ref.namelist()
            # Extrae el primer archivo (asumiendo que solo hay uno)
            primer_archivo = txt_file[0]
            file_content = zip_ref.read(primer_archivo)
            # Decodifica el contenido a texto (si es un archivo de texto)
            text_data = file_content.decode('utf-8')
            lines = text_data.strip().split('\n')
            self.proposal_line_ids.unlink()
            for line in lines[1:]:
                line_fields = line.split('|')
                if self.sire_type == 's':
                    line_fields.insert(8,'')
                    del line_fields[22:24]
                l10n_latam_identification_type_id = self.env['l10n_latam.identification.type'].search([('l10n_pe_vat_code','=', line_fields[11])], limit=1).id
                serie = line_fields[7]
                number = line_fields[9]
                name = serie[0] + ' ' + serie[1:] + '-' + number.zfill(8)
                move_id = self.env['account.move'].search([('name', '=', name),('partner_id.vat','=', line_fields[12]),('state', '=', 'posted')])
                partner_id = move_id.partner_id.id
                if not move_id:
                    partner_id = self.env['res.partner'].search([('vat','=', line_fields[12]),
                                                            ('parent_id','=',False),
                                                            ('l10n_latam_identification_type_id','=',l10n_latam_identification_type_id)]).id
                vals = {
                    'sire_sunat_id': self.id,
                    'issue_date': datetime.strptime(line_fields[4], "%d/%m/%Y").strftime("%Y-%m-%d"),
                    'l10n_latam_document_type_id': self.env['l10n_latam.document.type'].search([('code','=', line_fields[6])], limit=1).id,
                    'serie': serie,
                    'number': number,
                    'l10n_latam_identification_type_id': l10n_latam_identification_type_id,
                    'vat': line_fields[12],
                    'partner_id': partner_id,
                    'currency_id': self.env['res.currency'].search([('name','=', line_fields[25]),
                                                                    ('active','in', (True, False))]).id,
                    'exchange_rate': float(line_fields[26]),
                    'total': float(line_fields[24]),

                }
                self.env['proposal.line'].create(vals)

    def renew_proposal(self):
        self.proposal_ticket_number = ''
        self.proposal_ticket_date = False
        self.get_proposal()

    def get_proposal(self):
        token = self._get_token()
        headers = self._get_headers(token)
        period = self.period.strftime('%Y%m')
        try:
            # Si no existe el ticket, genera ticket para descargar
            proposal_response = False
            if not self.proposal_ticket_number:
                if self.sire_type == 'p':
                    proposal_url = f"https://api-sire.sunat.gob.pe/v1/contribuyente/migeigv/libros/rce/propuesta/web/propuesta/{period}/exportacioncomprobantepropuesta?codTipoArchivo=0&codOrigenEnvio=1"
                else:
                    proposal_url = f"https://api-sire.sunat.gob.pe/v1/contribuyente/migeigv/libros/rvie/propuesta/web/propuesta/{period}/exportapropuesta?codTipoArchivo=0"
                proposal_response = requests.get(proposal_url, headers=headers)
            if proposal_response and proposal_response.status_code == 200 or self.proposal_ticket_number:
                if not self.proposal_ticket_number:
                    self.proposal_ticket_number = proposal_response.json().get('numTicket')
                    self.proposal_ticket_date = datetime.utcnow()
                # else:
                #     self.unzip_file_create_lines(self.proposal_zip_file)
                #     return
                # Consultar Ticket
                ticket_response = self.get_ticket_info(period, headers, self.proposal_ticket_number)
                if ticket_response.status_code == 200:
                    # Descargar propuesta
                    json_data = ticket_response.json()
                    file_name = json_data.get('registros')[0]['archivoReporte'][0]['nomArchivoReporte']
                    codTipoAchivoReporte = json_data.get('registros')[0]['archivoReporte'][0].get('codTipoAchivoReporte','')
                    # codTipoAchivoReporte = ticket_response
                    zip_file = self.get_zip_file(file_name, codTipoAchivoReporte,period, headers)
                    if zip_file.status_code == 200:
                        self.unzip_file_create_lines(zip_file.content)
            else:
                raise UserError(proposal_response.text)
        except Exception as e:
            raise UserError(_(e))
        if self.proposal_ticket_number:
            self.state = 'proposal'
    
    def _get_first_last_day(self, date):
        # Obtener primer y ultimo dia del mes
        first_day = date.replace(day=1)
        last_day = (first_day + timedelta(days=32)).replace(day=1) - timedelta(days=1)
        return first_day, last_day
    
    def check_documents(self):
        for line in self.proposal_line_ids:
            if self.sire_type == 'p':
                move_type = ('in_invoice','in_refund')
            else:
                move_type = ('out_invoice','out_refund')
            modified_serie = f'{line.serie[0]} {line.serie[1:]}'
            domain = [
                ('move_type','in', move_type),
                ('invoice_date','=', line.issue_date),
                ('name','=', modified_serie + '-' + line.number.zfill(8)),
                #line.l10n_latam_document_type_id.doc_code_prefix + ' ' + line.serie + '-' + line.number.zfill(8)),
                # ('l10n_latam_document_type_id','=', line.l10n_latam_document_type_id.id),
                ('partner_id.vat','=', line.vat),
                ('state','=', 'posted'),
            ]
            #####################################################################
            # TODO Eliminar lineas porque son solo para poder programar mas rapido y 
            # llenar los datos de los clientes y los comprobantes
            #partner = self.env['res.partner'].search([('vat','=',line.vat)])
            #if not partner:
            #    partner = self.env['res.partner'].create({
            #        'name': 'Prueba',
            #        'l10n_latam_identification_type_id': line.l10n_latam_identification_type_id.id,
            #        'vat': line.vat,
            #    })
            #    partner.update_document()
            #invoice = self.env['account.move'].search(domain)
            #if not invoice:
            #    self.env['account.move'].create({
            #        #'move_type': 'out_invoice' if line.l10n_latam_document_type_id.id == 1 else 'out_refund',
            #        'move_type': 'in_invoice' if line.l10n_latam_document_type_id.id == 1 else 'in_refund',
            #        'date': line.issue_date,
            #        'ref': line.serie + '-' + line.number.zfill(8),
            #        'l10n_latam_document_type_id': line.l10n_latam_document_type_id.id,
            #        'partner_id': line.partner_id.id,
            #        'currency_id': line.currency_id.id,
            #        'invoice_line_ids': [Command.create({
            #            'name': 'prueba',
            #            'quantity': 1,
            #            'price_unit': line.total / 1.18,
            #            'tax_ids': [Command.link(61)],
            #        })]
            #    })
            ####################################################################
            document_found = self.env['account.move'].search(domain)
            if len(document_found) > 1:
                message = ''
                for document in document_found:
                    message += document.name + '\n' 
                raise UserError (_('There is more than 1 document with the same data in your system \n %s') % message)
            if document_found:
                line.state = 'ok'
                if round(1 / document_found.line_ids[0].currency_rate,3) != line.exchange_rate:
                    line.state = 'rate'
                if document_found.currency_id != line.currency_id:
                    line.state = 'currency'
                if abs(document_found.amount_total_signed) != abs(line.total):
                    line.state = 'amount'
                if document_found.date.month != line.issue_date.month:
                    line.state = 'account'
                line.account_move_id = document_found
            else:
                line.state = 'no'
        first_day, last_day = self._get_first_last_day(self.period)
        partner_annulled_id = self.company_id.partner_annulled_id
        if not partner_annulled_id:
            raise RedirectWarning(
                _('No este seleccionado el partner anulado'),
                self.env.ref('account.action_account_config').id,
                _("Go to the configuration panel"),
                )
        # odoo_invoices = self.env['account.move'].search([('date','>=', first_day),('date','<=', last_day), ('partner_id', '!=', partner_annulled_id.id), ('journal_id.ple_no_include','!=', True),
        #                                                 ('state','=','posted'),('move_type','in', ('in_invoice','in_refund') if self.sire_type == 'p' else ('out_invoice','out_refund'))])
        odoo_invoices = self.env['account.move'].search([('date','>=', first_day),('date','<=', last_day), ('state','=','posted'),('move_type','in', ('in_invoice','in_refund') if self.sire_type == 'p' else ('out_invoice','out_refund'))])
        #if len(odoo_invoices) > len(self.proposal_line_ids):
        self.account_move_ids = [Command.clear()]
        for invoice in odoo_invoices:
            if invoice not in self.proposal_line_ids.account_move_id:
                self.account_move_ids = [Command.link(invoice.id)]
        self.state = 'check'

    def delete_records_not_in_proposal(self):
        self.account_move_ids = [Command.clear()]

    def accept_proposal(self):
        token = self._get_token()
        headers = self._get_headers(token)
        period = self.period.strftime('%Y%m')
        try:
            if self.sire_type == 'p':
                accept_url = f"https://api-sire.sunat.gob.pe/v1/contribuyente/migeigv/libros/rce/propuesta/web/registroslibros/{period}/aceptarpropuesta"
            else:
                accept_url = f"https://api-sire.sunat.gob.pe/v1/contribuyente/migeigv/libros/rvie/propuesta/web/propuesta/{period}/aceptapropuesta"
            accept_response = requests.post(accept_url, headers=headers)
            if accept_response.status_code == 200:
                self.state = 'register'
            else:
                raise UserError(accept_response.text)
        except Exception as e:
            raise UserError(e)

    def delete_preliminary(self):
        token = self._get_token()
        headers = self._get_headers(token)
        period = self.period.strftime('%Y%m')
        try:
            if self.sire_type == 'p':
                delete_url = f"https://api-sire.sunat.gob.pe/v1/contribuyente/migeigv/libros/rce/preliminar/web/registroslibros/{period}/1/eliminapreliminar"
            else:
                delete_url = f"https://api-sire.sunat.gob.pe/v1/contribuyente/migeigv/libros/rvierce/gestionlibro/web/registroslibros/{period}/eliminarreemplazo?codLibro=140000"
            delete_response = requests.put(delete_url, headers=headers)
            if delete_response.status_code == 200:
                self.state = 'check'
                self.preliminary_ticket_number = ''
                self.preliminary_ticket_date = False
                self.preliminary_zip_file = False
            else:
                raise UserError(delete_response.text)
        except Exception as e:
            raise UserError(e)

    def _get_serie_folio(self, number):
        values = {"serie": "", "folio": ""}
        number_matchs = [rn for rn in re.finditer("\\d+", number or "")]
        if number_matchs:
            last_number_match = number_matchs[-1]
            values["serie"] = number[: last_number_match.start()].replace("-", "") or ""
            values["folio"] = last_number_match.group() or ""
        return values
    
    def _get_rce_content_8_4(self):
        lines = self._get_preliminary_data()
        content = ''
        for line in lines:
            columns = line
            # if columns["currency"] != self.company_id.currency_id.name:
            #     total = str("%.2f" % ((columns["amount_total"] or 0) / abs(columns["rate"]) or 0))
            #     base_igv = str("%.2f" % ((columns["base_igv"] or 0) / abs(columns["rate"]) or 0))
            #     tax_igv = str("%.2f" % ((columns["tax_igv"] or 0) / abs(columns["rate"]) or 0))
            #     base_igv_g_ng = str("%.2f" % ((columns["base_igv_g_ng"] or 0) / abs(columns["rate"]) or 0))
            #     vat_igv_g_ng = str("%.2f" % ((columns["vat_igv_g_ng"] or 0) / abs(columns["rate"]) or 0))
            #     base_igv_ng = str("%.2f" % ((columns["base_igv_ng"] or 0) / abs(columns["rate"]) or 0))
            #     vat_igv_ng = str("%.2f" % ((columns["vat_igv_ng"] or 0) / abs(columns["rate"]) or 0))
            #     val_adq = str("%.2f" % ((sum([columns["base_exo"] or 0, columns["base_ina"] or 0, columns["base_free"] or 0]) or 0) / abs(columns["rate"]) or 0))
            #     tax_isc = str("%.2f" % ((columns["tax_isc"] or 0) / abs(columns["rate"]) or 0))
            #     vat_icbper = str("%.2f" % ((columns["vat_icbper"] or 0) / abs(columns["rate"]) or 0))
            #     vat_other = str("%.2f" % ((columns["vat_other"] or 0) / abs(columns["rate"]) or 0))
            # else:
            total = str("%.2f" % (columns["amount_total"] or 0))
            base_igv = str("%.2f" % (columns["base_igv"] or 0))
            tax_igv = str("%.2f" % (columns["tax_igv"] or 0))
            base_igv_g_ng = str("%.2f" % (columns["base_igv_g_ng"] or 0))
            vat_igv_g_ng = str("%.2f" % (columns["vat_igv_g_ng"] or 0))
            base_igv_ng = str("%.2f" % (columns["base_igv_ng"] or 0))
            vat_igv_ng = str("%.2f" % (columns["vat_igv_ng"] or 0))
            val_adq = str("%.2f" % (sum([columns["base_exo"] or 0, columns["base_ina"] or 0, columns["base_free"] or 0]) or 0))
            tax_isc = str("%.2f" % (columns["tax_isc"] or 0))
            vat_icbper = str("%.2f" % (columns["vat_icbper"] or 0))
            vat_other = str("%.2f" % (columns["vat_other"] or 0))
            serie_folio = self._get_serie_folio(columns["move_name"])
            serie_folio_related = self._get_serie_folio(columns["related_document"])
            content += columns["company_vat"] + '|' + \
                columns["company_name"] + '|' + \
                self.period.strftime('%Y%m') + '||' + \
                (columns["invoice_date"].strftime("%d/%m/%Y") if columns["invoice_date"] else "") + '|' + \
                (columns["date_due"].strftime("%d/%m/%Y") if columns["date_due"] else "" or '') + '|' + \
                columns["document_type"] + '|' + \
                serie_folio["serie"].replace(" ", "") + '|' + \
                (str(columns["invoice_date"].year) if columns["invoice_date"] and columns["document_type"] in ("50", "52") else "") + '|' + \
                serie_folio["folio"].lstrip('0') + '||' + \
                columns["partner_lit_code"] + '|' + \
                (columns["customer_vat"] or "") + '|' + \
                columns["customer"] + '|' + \
                base_igv + '|' + \
                tax_igv + '|' + \
                base_igv_g_ng + '|' + \
                vat_igv_g_ng + '|' + \
                base_igv_ng + '|' + \
                vat_igv_ng + '|' + \
                val_adq + '|' + \
                tax_isc + '|' + \
                vat_icbper + '|' + \
                vat_other + '|' + \
                total + '|' + \
                columns["currency"] + '|' + \
                str(("%.3f" % abs(columns["rate"])) if columns["currency"] != self.company_id.currency_id.name else "1.000") + '|' + \
                (columns["emission_date_related"].strftime("%d/%m/%Y") if columns["emission_date_related"] else "") + '|' + \
                (columns["document_type_related"] or "") + '|' + \
                serie_folio_related.get("serie", "").replace(" ", "") + '|' + \
                (serie_folio["serie"].replace(" ", "") if columns["document_type"] in ("50", "52") else "") + '|' + \
                serie_folio_related.get("folio", "").replace(" ", "").lstrip("0") + '||||0.00||' + \
                (columns["detraction_number"] or "") + '||1|0|||||||||||||||||||||||||||||||||||||||\n'
        return content
    
    # despues de el campo periodo y quitar | al final
    # self.get_car(columns, serie_folio) + '|' + \
            
    def _get_rvie_content_14_2(self):
        lines = self._get_preliminary_data()
        content = ''
        state_error = []
        for line in lines:
            columns = line
            # if columns["status"] == "posted" and columns["edi_state"] != "sent":
            #     state_error.append(columns["move_name"])
            #     continue
            # if columns["currency"] != self.company_id.currency_id.name:
            #     total = str("%.2f" % ((columns["amount_total"] or 0) / abs(columns["rate"]) or 0))
            #     base_exp = str("%.2f" % ((columns["base_exp"] or 0) / abs(columns["rate"]) or 0))
            #     base_igv = str("%.2f" % ((columns["base_igv"] or 0) / abs(columns["rate"]) or 0))
            #     tax_igv = str("%.2f" % ((columns["tax_igv"] or 0) / abs(columns["rate"]) or 0))
            #     base_exo = str("%.2f" % ((columns["base_exo"] or 0) / abs(columns["rate"]) or 0))
            #     base_ina = str("%.2f" % ((columns["base_ina"] or 0) / abs(columns["rate"]) or 0))
            #     base_ivap = str("%.2f" % ((columns["base_ivap"] or 0) / abs(columns["rate"]) or 0))
            #     tax_ivap = str("%.2f" % ((columns["tax_ivap"] or 0) / abs(columns["rate"]) or 0))
            #     tax_isc = str("%.2f" % ((columns["tax_isc"] or 0) / abs(columns["rate"]) or 0))
            #     vat_icbper = str("%.2f" % ((columns["vat_icbper"] or 0) / abs(columns["rate"]) or 0))
            #     vat_other = str("%.2f" % ((columns["vat_other"] or 0) / abs(columns["rate"]) or 0))
            # else:
            total = str("%.2f" % (columns["amount_total"] or 0))
            base_exp = str("%.2f" % (columns["base_exp"] or 0))
            base_igv = str("%.2f" % (columns["base_igv"] or 0))
            tax_igv = str("%.2f" % (columns["tax_igv"] or 0))
            base_exo = str("%.2f" % (columns["base_exo"] or 0))
            base_ina = str("%.2f" % (columns["base_ina"] or 0))
            base_ivap = str("%.2f" % (columns["base_ivap"] or 0))
            tax_ivap = str("%.2f" % (columns["tax_ivap"] or 0))
            tax_isc = str("%.2f" % (columns["tax_isc"] or 0))
            vat_icbper = str("%.2f" % (columns["vat_icbper"] or 0))
            vat_other = str("%.2f" % (columns["vat_other"] or 0))
            serie_folio = self._get_serie_folio(columns["move_name"])
            serie_folio_related = self._get_serie_folio(columns["related_document"])
            content += columns["company_vat"] + '|' + \
                    columns["company_name"] + '|' + \
                    self.period.strftime('%Y%m') + '||' + \
                    (columns["invoice_date"].strftime("%d/%m/%Y") if columns["invoice_date"] else "") + '|' + \
                    (columns["date_due"].strftime("%d/%m/%Y") if columns["date_due"] else "" or '') + '|' + \
                    columns["document_type"] + '|' + \
                    serie_folio["serie"].replace(" ", "") + '|' + \
                    serie_folio["folio"].lstrip('0') + '||' + \
                    columns["partner_lit_code"] + '|' + \
                    (columns["customer_vat"] or "") + '|' + \
                    columns["customer"] + '|' + \
                    base_exp + '|' + \
                    base_igv + '|0.00|' + \
                    tax_igv + '|0.00|' + \
                    base_exo + '|' + \
                    base_ina + '|' + \
                    tax_isc + '|' + \
                    base_ivap + '|' + \
                    tax_ivap + '|' + \
                    vat_icbper + '|' + \
                    vat_other + '|' + \
                    total + '|' + \
                    columns["currency"] + '|' + \
                    str(("%.3f" % abs(columns["rate"])) if columns["currency"] != self.company_id.currency_id.name else "1.000") + '|' + \
                    (columns["emission_date_related"].strftime("%d/%m/%Y") if columns["emission_date_related"] else "") + '|' + \
                    (columns["document_type_related"] or "") + '|' + \
                    serie_folio_related.get("serie", "").replace(" ", "") + '|' + \
                    serie_folio_related.get("folio", "").replace(" ", "").lstrip("0") + '|||||||||||||||||||'
        if state_error:
            raise UserError(_('Documents posted with edi_state not sent: \n %s') %state_error)
        return content

    def send_preliminary(self):
        if len(self.proposal_line_ids.account_move_id + self.account_move_ids) == 0:
            raise UserError(_('It\'s not possible to replace proposal because there is no documents matched and no documents in the system.'))
        if self.sire_type == 'p':
            content = self._get_rce_content_8_4()
            tus_endpoint = 'https://api-sire.sunat.gob.pe/v1/contribuyente/migeigv/libros/rvierce/receptorpropuesta/web/propuesta/upload'
            codLibro = "080000"
            codProceso = "61"
        else:
            content = self._get_rvie_content_14_2()
            tus_endpoint = 'https://api-sire.sunat.gob.pe/v1/contribuyente/migeigv/libros/rvierce/receptorpropuesta/web/propuesta/upload'
            codLibro = "140000"
            codProceso = "3"
        memory_txt_file = io.BytesIO(content.encode())
        memory_zip_file = io.BytesIO()
        with zipfile.ZipFile(memory_zip_file, "w") as zipf:
            zipf.writestr(self._get_file_name() + '.TXT', memory_txt_file.getvalue())
        memory_zip_file.seek(0)
        token = self._get_token()

        # # Después de crear el archivo ZIP en memoria
        # zip_file_path = '/home/pollo/Descargas/' + self._get_file_name() + '.zip'  # Ruta donde deseas guardar el archivo ZIP

        # with open(zip_file_path, "wb") as zip_file:
        #     zip_file.write(memory_zip_file.getvalue())

        # Guardar el archivo ZIP en el campo
        self.write({'preliminary_zip_file': base64.b64encode(memory_zip_file.read())})

        # Parámetros requeridos
        filename = self._get_file_name() + '.zip'
        filetype = "application/zip"
        numRuc = self.company_id.partner_id.vat
        perTributario = self.period.strftime('%Y%m')
        codOrigenEnvio = "2"
        codTipoCorrelativo = "01"
        nomArchivoImportacion = self._get_file_name() + '.zip'

        # Headers (metadata)
        headers = {
            "Authorization": "Bearer " + token,
        }
        metadata = {
            "filename": filename,
            "filetype": filetype,
            "numRuc": numRuc,
            "perTributario": perTributario,
            "codOrigenEnvio": codOrigenEnvio,
            "codProceso": codProceso,
            "codTipoCorrelativo": codTipoCorrelativo,
            "nomArchivoImportacion": nomArchivoImportacion,
            "codLibro": codLibro,
        }
        tus_client = client.TusClient(tus_endpoint, headers=headers)

        # Crear el uploader de TUS con el archivo ZIP
        uploader = tus_client.uploader(file_stream=memory_zip_file, metadata=metadata, chunk_size=20000)

        # Subir el archivo ZIP al servidor TUS
        try:
            uploader.upload()
            # Obtener el número de ticket de envío
            response = uploader.request
            if response.status_code == 200:
                self.preliminary_ticket_number = response.response_content
                self.preliminary_ticket_date = datetime.utcnow()
                self.state = 'preliminary'
            else:
                raise UserError(response.text)
        except Exception as e:
            # if e.status_code == 422:
            #     self.state = 'preliminary'
            # else:
            raise UserError(e.response_content)
        
    def register_preliminary(self):
        token = self._get_token()
        headers = self._get_headers(token)
        period = self.period.strftime('%Y%m')
        try:
            if self.sire_type == 'p':
                register_url = f"https://api-sire.sunat.gob.pe/v1/contribuyente/migeigv/libros/rce/preliminar/web/registroslibros/{period}/registrapreliminares"
            else:
                register_url = f"https://api-sire.sunat.gob.pe/v1/contribuyente/migeigv/libros/rvierce/gestionlibro/web/registroslibros/{period}/registrapreliminar"
            register_response = requests.post(register_url, headers=headers)
            if register_response.status_code == 200:
                self.state = 'register'
            else:
                raise UserError(register_response.text)
        except Exception as e:
            raise UserError(e)

    def cancel(self):
        if self.state == 'register':
            if self.preliminary_ticket_number:
                self.state = 'preliminary'
            else:
                self.state = 'check'
            warning = {
                'title': _('Sire SUNAT'),
                'message': _('You should delete the registration in SOL SUNAT portal manually!'),
                'type': 'notification',
            }
            return {'warning': warning}
        if self.state == 'preliminary':
            self.delete_preliminary()
            self.state = 'check'
            return
        if self.state == 'check':
            self.account_move_ids = [Command.clear()]
            self.state = 'proposal'
            return
        self.state = 'draft'
        self.proposal_line_ids.unlink()

    def _get_file_name(self):
        if self.sire_type == 'p':
            book_code = '080400'
        else:
            book_code = '140400'
        oportunity = '02'
        filename = "LE"+ self.company_id.partner_id.vat + self.period.strftime('%Y%m').ljust(8, '0') + book_code + oportunity + '1112'
        return filename
    
    def _get_zip_file_name(self):
        filename = self.company_id.partner_id.vat + '-CP-' + self.period.strftime('%Y%m') + '-01'
        return filename
            
    def get_car(self, columns, serie_folio):
        car = columns["customer_vat"][-11:].zfill(11) + columns["document_type"] + serie_folio["serie"].replace(" ", "")[-4:].zfill(4) + serie_folio["folio"][-10:].zfill(10)
        return car

    def build_result_dict(self, query_res_lines):
        result = {
            "document_type": None,
            "date": None,
            "customer_vat": None,
            "customer": None,
            "amount_total": None,
            "invoice_date": None,
            "base_exp": None,
            "base_igv": None,
            "tax_igv": None,
            "base_exo": None,
            "base_ina": None,
            "tax_isc": None,
            "base_ivap": None,
            "tax_ivap": None,
            "vat_icbper": None,
            "vat_igv_g_ng": None,
            "vat_igv_ng": None,
            "base_free": None,
            "vat_other": None,
            "base_withholdings": None,
        }
        if query_res_lines:
            sign_total = -1 if query_res_lines["move_type"] in ("out_invoice", "out_refund") else 1
            rate = (
                (query_res_lines["amount_currency"] / query_res_lines["total"])
                if query_res_lines["total"]
                else 1
            )
            refund = query_res_lines["reversed_entry_name"]
            result = {
                "move_name": query_res_lines["move_name"],
                "invoice_date": query_res_lines["invoice_date"],
                "date": query_res_lines["date"],
                "date_due": query_res_lines["invoice_date_due"],
                "document_type": query_res_lines["document_type"],
                "partner_lit": query_res_lines["partner_lit"],
                "partner_lit_code": query_res_lines["partner_lit_code"],
                "id_number": query_res_lines["partner_vat"],
                "customer_vat": query_res_lines["partner_vat"],
                "customer": query_res_lines["partner_name"],
                "amount_total": query_res_lines["amount_currency"] * (sign_total * -1),
                "currency": query_res_lines["currency_name"],
                "rate": abs(rate),
                "base_igv": (query_res_lines["base_igv"] or 0) * sign_total,
                "tax_igv": (query_res_lines["vat_igv"] or 0) * sign_total,
                "base_igv_g_ng": query_res_lines["base_igv_g_ng"],
                "vat_igv_g_ng": query_res_lines["vat_igv_g_ng"],
                "base_igv_ng": query_res_lines["base_igv_ng"],
                "vat_igv_ng": query_res_lines["vat_igv_ng"],
                "base_exo": (query_res_lines["base_exo"] or 0) * sign_total,
                "base_ina": (query_res_lines["base_ina"] or 0) * sign_total,
                "base_ivap": (query_res_lines["vat_ivap"] or 0) * sign_total,
                "base_exp": (query_res_lines["base_exp"] or 0) * sign_total,
                "tax_ivap": (query_res_lines["vat_ivap"] or 0) * sign_total,
                "vat_icbper": (query_res_lines["vat_icbper"] or 0) * sign_total,
                "tax_isc": (query_res_lines["vat_isc"] or 0) * sign_total,
                "base_free": query_res_lines["base_free"],
                "vat_other": query_res_lines["vat_other"],
                "base_withholdings": query_res_lines["base_withholding"],
                "detraction_date": query_res_lines["detraction_date"],
                "detraction_number": query_res_lines["detraction_number"],
                "emission_date_related": query_res_lines["reversed_entry_date"]
                if refund
                else query_res_lines["debit_origin_date"],
                "document_type_related": query_res_lines["reversed_entry_document_type"]
                if refund
                else query_res_lines["debit_origin_document_type"],
                "related_document": query_res_lines["reversed_entry_name"]
                if refund
                else query_res_lines["debit_origin_name"],
                "status": query_res_lines["state"],
                "edi_state": query_res_lines["edi_state"],
                "invoice_dua_name": query_res_lines["invoice_dua_name"],
                "invoice_dua_document_type": query_res_lines["invoice_dua_document_type"],
                "invoice_dua_date": query_res_lines["invoice_dua_date"],
                "partner_country_code": query_res_lines["partner_country_code"],
                "partner_street": query_res_lines["partner_street"],
                "partner_country_agreement_code": query_res_lines["partner_country_agreement_code"],
                "usage_type_code": query_res_lines["usage_type_code"],
                "service_modality": query_res_lines["service_modality"],
                "company_vat": query_res_lines["company_vat"],
                "company_name": query_res_lines["company_name"],
            }
        return result

    def _get_preliminary_data(self):
        company_id = self.company_id.id
        move_ids = tuple((self.proposal_line_ids.filtered(lambda l: l.state not in ('no','account')).account_move_id + self.account_move_ids).ids)
        where_clause = '((((((("account_move_line"."display_type" not in %s) OR "account_move_line"."display_type" IS NULL) AND ("account_move_line"."company_id" in (%s))))) AND ("account_move_line"."parent_state" = %s)) AND (("account_move_line__move_id"."always_tax_exigible" = %s) OR (("account_move_line"."tax_line_id" IS NULL  AND NOT EXISTS ( SELECT 1 FROM "account_move_line_account_tax_rel" AS "account_move_line__tax_ids" WHERE "account_move_line__tax_ids"."account_move_line_id" = "account_move_line".id)) OR ("account_move_line__move_id"."tax_cash_basis_rec_id" IS NOT NULL OR (("account_move_line"."tax_line_id" in (SELECT "account_tax".id FROM "account_tax" WHERE (("account_tax"."tax_exigibility" != %s) OR "account_tax"."tax_exigibility" IS NULL) AND ("account_tax"."company_id" IS NULL OR ("account_tax"."company_id" in (%s))))) OR EXISTS ( SELECT 1 FROM "account_move_line_account_tax_rel" AS "account_move_line__tax_ids" WHERE "account_move_line__tax_ids"."account_move_line_id" = "account_move_line".id AND "account_move_line__tax_ids"."account_tax_id" IN (SELECT "account_tax".id FROM "account_tax" WHERE (("account_tax"."tax_exigibility" != %s) OR "account_tax"."tax_exigibility" IS NULL) AND ("account_tax"."company_id" IS NULL  OR ("account_tax"."company_id" in (%s)))))))))) AND ("account_move_line"."company_id" IS NULL  OR ("account_move_line"."company_id" in (%s))) AND (account_move_line.move_id in %s)'
        where_params = [('line_section', 'line_note'), company_id, 'posted', True, 'on_payment', company_id, 'on_payment', company_id, company_id, move_ids]

        ref = self.env.ref
        cid = self.company_id.id
        try:
            tax_group_igv = ref(f"account.{cid}_tax_group_igv").id
            tax_group_igv_g_ng = ref(f"account.{cid}_tax_group_igv_g_ng").id
            tax_group_igv_ng = ref(f"account.{cid}_tax_group_igv_ng").id
            tax_group_exp = ref(f"account.{cid}_tax_group_exp").id
            tax_group_exo = ref(f"account.{cid}_tax_group_exo").id
            tax_group_ina = ref(f"account.{cid}_tax_group_ina").id
            tax_group_ivap = ref(f"account.{cid}_tax_group_ivap").id
            tax_group_icbper = ref(f"account.{cid}_tax_group_icbper").id
            tax_group_isc = ref(f"account.{cid}_tax_group_isc").id
            tax_group_gra = ref(f"account.{cid}_tax_group_gra").id
            tax_group_other = ref(f"account.{cid}_tax_group_other").id
            tax_group_ret = ref(f"account.{cid}_tax_group_ret").id
        except ValueError:
            raise UserError(_("In order to generate the PLE reports, please update account module to update the required data."))

        query = f"""
SELECT
    account_move_line__move_id.id,
    account_move_line__move_id.name as move_name,
    account_move_line__move_id.ref as move_ref,
    account_move_line__move_id.edi_state,
    rp.name as partner_name,
    rp.vat as partner_vat,
    rp.street as partner_street,
    lit.name->>'en_US' as partner_lit,
    lit.l10n_pe_vat_code as partner_lit_code,
    rp.country_id as partner_country_id,
    rpc.l10n_pe_code as partner_country_code,
    rpc.l10n_pe_agreement_code as partner_country_agreement_code,
    account_move_line__move_id.currency_id,
    rc.name as currency_name,
    account_move_line__move_id__l10n_latam_document_type_id.code as document_type,
    account_move_line__move_id.l10n_pe_detraction_date as detraction_date,
    account_move_line__move_id.l10n_pe_detraction_number as detraction_number,
    account_move_line__move_id.l10n_pe_service_modality as service_modality,
    account_move_line__move_id.l10n_pe_usage_type_id as usage_type_id,
    lprt.code as usage_type_code,
    account_move_line__move_id.id as move_id,
    account_move_line__move_id.move_type,
    account_move_line__move_id.date,
    account_move_line__move_id.invoice_date,
    account_move_line__move_id.invoice_date_due,
    account_move_line__move_id.partner_id,
    account_move_line__move_id.journal_id,
    account_move_line__move_id.name,
    account_move_line__move_id.l10n_latam_document_type_id as l10n_latam_document_type_id,
    account_move_line__move_id.state,
    account_move_line__move_id.company_id,
    dua.name as invoice_dua_name,
    dua.invoice_date as invoice_dua_date,
    dua.l10n_latam_document_type_id as invoice_dua_document_type_id,
    ldt_dua.code as invoice_dua_document_type,
    reversed_entry.name as reversed_entry_name,
    reversed_entry.invoice_date as reversed_entry_date,
    reversed_entry.l10n_latam_document_type_id as reversed_entry_document_type_id,
    ldt_reversed_entry.code as reversed_entry_document_type,
    debit_origin.name as debit_origin_name,
    debit_origin.invoice_date as debit_origin_date,
    debit_origin.l10n_latam_document_type_id as debit_origin_document_type_id,
    ldt_debit_origin.code as debit_origin_document_type,
    partner_company.vat  AS company_vat,
    company.name AS company_name,
    sum(CASE WHEN btg.id = {tax_group_igv}
        THEN account_move_line.balance ELSE Null END) as base_igv,
    sum(CASE WHEN ntg.id = {tax_group_igv}
        THEN account_move_line.balance ELSE Null END) as vat_igv,
    sum(CASE WHEN btg.id = {tax_group_igv_g_ng}
        THEN account_move_line.balance ELSE Null END) as base_igv_g_ng,
    sum(CASE WHEN ntg.id = {tax_group_igv_g_ng}
        THEN account_move_line.balance ELSE Null END) as vat_igv_g_ng,
    sum(CASE WHEN btg.id = {tax_group_igv_ng}
        THEN account_move_line.balance ELSE Null END) as base_igv_ng,
    sum(CASE WHEN ntg.id = {tax_group_igv_ng}
        THEN account_move_line.balance ELSE Null END) as vat_igv_ng,
    sum(CASE WHEN btg.id = {tax_group_exp}
        THEN account_move_line.balance ELSE Null END) as base_exp,
    sum(CASE WHEN ntg.id = {tax_group_exp}
        THEN account_move_line.balance ELSE Null END) as vat_exp,
    sum(CASE WHEN btg.id = {tax_group_exo}
        THEN account_move_line.balance ELSE Null END) as base_exo,
    sum(CASE WHEN ntg.id = {tax_group_exo}
        THEN account_move_line.balance ELSE Null END) as vat_exo,
    sum(CASE WHEN btg.id = {tax_group_ina}
        THEN account_move_line.balance ELSE Null END) as base_ina,
    sum(CASE WHEN ntg.id = {tax_group_ina}
        THEN account_move_line.balance ELSE Null END) as vat_ina,
    sum(CASE WHEN btg.id = {tax_group_ivap}
        THEN account_move_line.balance ELSE Null END) as base_ivap,
    sum(CASE WHEN ntg.id = {tax_group_ivap}
        THEN account_move_line.balance ELSE Null END) as vat_ivap,
    sum(CASE WHEN btg.id = {tax_group_icbper}
        THEN account_move_line.balance ELSE Null END) as base_icbper,
    sum(CASE WHEN ntg.id = {tax_group_icbper}
        THEN account_move_line.balance ELSE Null END) as vat_icbper,
    sum(CASE WHEN btg.id = {tax_group_isc}
        THEN account_move_line.balance ELSE Null END) as base_isc,
    sum(CASE WHEN ntg.id = {tax_group_isc}
        THEN account_move_line.balance ELSE Null END) as vat_isc,
    sum(CASE WHEN btg.id = {tax_group_gra}
        THEN account_move_line.balance ELSE Null END) as base_free,
    sum(CASE WHEN ntg.id = {tax_group_gra}
        THEN account_move_line.balance ELSE Null END) as vat_free,
    sum(CASE WHEN btg.id = {tax_group_other}
        THEN account_move_line.balance ELSE Null END) as base_other,
    sum(CASE WHEN ntg.id = {tax_group_other}
        THEN account_move_line.balance ELSE Null END) as vat_other,
    sum(CASE WHEN btg.id = {tax_group_ret}
        THEN account_move_line.balance ELSE Null END) as base_withholding,
    sum(CASE WHEN ntg.id = {tax_group_ret}
        THEN account_move_line.balance ELSE Null END) as vat_withholding,
    account_move_line__move_id.amount_total as total,
    account_move_line__move_id.amount_total_signed as amount_currency
FROM
    account_move_line
LEFT JOIN
    account_move as account_move_line__move_id
    ON account_move_line.move_id = account_move_line__move_id.id
LEFT JOIN
    -- nt = net tax
    account_tax AS nt
    ON account_move_line.tax_line_id = nt.id
LEFT JOIN
    account_move_line_account_tax_rel AS account_move_linetr
    ON account_move_line.id = account_move_linetr.account_move_line_id
LEFT JOIN
    -- bt = base tax
    account_tax AS bt
    ON account_move_linetr.account_tax_id = bt.id
LEFT JOIN
    account_tax_group AS btg
    ON btg.id = bt.tax_group_id
LEFT JOIN
    account_tax_group AS ntg
    ON ntg.id = nt.tax_group_id
LEFT JOIN
    res_partner AS rp
    ON rp.id = account_move_line__move_id.commercial_partner_id
LEFT JOIN
    res_country AS rpc
    ON rpc.id = rp.country_id
LEFT JOIN
    l10n_latam_identification_type AS lit
    ON rp.l10n_latam_identification_type_id = lit.id
LEFT JOIN
    res_currency AS rc
    ON rc.id = account_move_line__move_id.currency_id
LEFT JOIN
    l10n_latam_document_type AS account_move_line__move_id__l10n_latam_document_type_id
    ON account_move_line__move_id__l10n_latam_document_type_id.id = account_move_line__move_id.l10n_latam_document_type_id
LEFT JOIN
    account_move AS reversed_entry
    ON reversed_entry.id = account_move_line__move_id.reversed_entry_id
LEFT JOIN
    l10n_latam_document_type AS ldt_reversed_entry
    ON ldt_reversed_entry.id = reversed_entry.l10n_latam_document_type_id
LEFT JOIN
    account_move AS debit_origin
    ON debit_origin.id = account_move_line__move_id.debit_origin_id
LEFT JOIN
    l10n_latam_document_type AS ldt_debit_origin
    ON ldt_debit_origin.id = debit_origin.l10n_latam_document_type_id
LEFT JOIN
    account_move AS dua
    ON dua.id = account_move_line__move_id.l10n_pe_dua_invoice_id
LEFT JOIN
    l10n_latam_document_type AS ldt_dua
    ON ldt_dua.id = dua.l10n_latam_document_type_id
LEFT JOIN
    l10n_pe_ple_usage AS lprt
    ON lprt.id = account_move_line__move_id.l10n_pe_usage_type_id
LEFT JOIN
    account_journal AS aj
    ON aj.id = account_move_line__move_id.journal_id
LEFT JOIN
    res_company AS company
    ON company.id = account_move_line__move_id.company_id
LEFT JOIN
    res_partner AS partner_company
    ON partner_company.id = company.partner_id
WHERE
    {where_clause}
    AND (account_move_line.tax_line_id is not null or btg.l10n_pe_edi_code is not null)
    AND aj.l10n_latam_use_documents
GROUP BY
    account_move_line__move_id.id, rp.id, lit.id, rc.id, account_move_line__move_id__l10n_latam_document_type_id.id,
    reversed_entry.id, ldt_reversed_entry.id, debit_origin.id,
    ldt_debit_origin.id, dua.id, ldt_dua.id, rpc.id, lprt.id, company.id, partner_company.id
ORDER BY
    account_move_line__move_id.date, account_move_line__move_id.name
        """

        self.env.cr.execute(query, where_params)
        query_res_lines = self.env.cr.dictfetchall()

        result = []
        for line in query_res_lines:
            result.append(self.build_result_dict(line))
        
        return result
    
class ProposalLine(models.Model):
    _name = 'proposal.line'
    _description = 'Proposal Line'

    sire_sunat_id = fields.Many2one('sire.sunat', string='Sire Sunat')
    issue_date = fields.Date('Issue Date')
    # due_date = fields.Date('Due Date')
    l10n_latam_document_type_id = fields.Many2one('l10n_latam.document.type', string='Document Type')
    serie = fields.Char('Serie')
    # year = fields.Char('Year')
    number = fields.Char('Number')
    # final_no = fields.Char('Final Number (Range)')
    l10n_latam_identification_type_id = fields.Many2one('l10n_latam.identification.type', string='Identification Type')
    vat = fields.Char('Vat')
    partner_id = fields.Many2one('res.partner', string='Partner')
    # taxable_tb_to = fields.Float('Taxable TB TO')
    # tax_to = fields.Float('Tax TO')
    # taxable_tb_touo = fields.Float('Taxable TB TOUO')
    # tax_touo = fields.Float('Tax TOUO')
    # taxable_tb_uo = fields.Float('Taxable TB UO')
    # tax_uo = fields.Float('Tax UO')
    # adq_value_uo = fields.Float('Adq. Value UO')
    # isc = fields.Float('ISC')
    # icbper = fields.Float('ICBPER')
    # other = fields.Float('Other')
    currency_id = fields.Many2one('res.currency', string='Currency')
    exchange_rate = fields.Float('Exchange Rate', digits=(6,3))
    total = fields.Float('Total')
    state = fields.Selection([
        ('to_match','To Match'),
        ('ok', 'Matched'),
        ('no', 'Unmatched'),
        ('amount', 'Amount Check'),
        ('currency', 'Currency Check'),
        ('rate', 'Rate Check'),
        ('account', 'Accounting Date Check'),
    ], string='State', default='to_match')
    account_move_id = fields.Many2one('account.move', string='Invoice')
