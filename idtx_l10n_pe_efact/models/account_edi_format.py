# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import base64
from requests.exceptions import ConnectionError as ReqConnectionError, HTTPError, ReadTimeout
from odoo.tools.zeep.wsse.username import UsernameToken
from odoo.tools.zeep import Client, Settings
from lxml import etree
from lxml import objectify
from odoo.tools import html_escape

from odoo import models, api, _

from zeep.transports import Transport

class DebugTransport(Transport):
    def post_xml(self, address, envelope, headers):
        # quitar encabezados WSA generados por zeep
        print(envelope)
        for n in envelope.xpath('//wsa:*', namespaces={'wsa': 'http://www.w3.org/2005/08/addressing'}):
            n.getparent().remove(n)
        return super().post_xml(address, envelope, headers)
    
class AccountEdiFormat(models.Model):
    _inherit = 'account.edi.format'

    def _l10n_pe_edi_get_efact_credentials(self, company):
        self.ensure_one()
        res = {'fault_ns': 'soap-env'}
        if company.l10n_pe_edi_test_env:
            res.update({
                'wsdl': 'https://ose-gw1.efact.pe/ol-ti-itcpe/billService?wsdl',
                'token': UsernameToken('20606070579', 'q70qc0J8S6'),
            })
        else:
            res.update({
                'wsdl': 'https://ose-gw1.efact.pe/ol-ti-itcpe/billService?wsdl',
                'token': UsernameToken(company.sudo().l10n_pe_edi_provider_username, company.sudo().l10n_pe_edi_provider_password),
            })
        return res

    def _l10n_pe_edi_sign_invoices_efact(self, invoice, edi_filename, edi_str):
        return self._l10n_pe_edi_sign_service_efact(invoice.company_id, edi_filename, edi_str, invoice.l10n_latam_document_type_id.code)

    def _l10n_pe_edi_sign_service_efact(self, company, edi_filename, edi_str, latam_document_type):
        credentials = self._l10n_pe_edi_get_efact_credentials(company)
        if not company.sudo().l10n_pe_edi_certificate_id:
            return {'error': _("No valid certificate found for %s company.", company.display_name)}

        # Sign the document.
        edi_tree = objectify.fromstring(edi_str)
        edi_tree = self._l10n_pe_sign(company.sudo().l10n_pe_edi_certificate_id, edi_tree)
        edi_str = etree.tostring(edi_tree, xml_declaration=True, encoding='ISO-8859-1')

        zip_edi_str = self._l10n_pe_edi_zip_edi_document([('%s.xml' % edi_filename, edi_str)])
        try:
            settings = Settings(raw_response=True)
            client = Client(
                wsdl=credentials['wsdl'],
                wsse=credentials['token'],
                settings=settings,
                operation_timeout=15,
                timeout=15,
                transport=DebugTransport(),
            )
            result = client.service.sendBill('%s.zip' % edi_filename, zip_edi_str)
            if result.status_code != 500:
                result.raise_for_status()
        except (ReqConnectionError, HTTPError, TypeError, ReadTimeout):
            return {'error': self._l10n_pe_edi_get_general_error_messages()['L10NPE08'], 'blocking_level': 'warning'}
        soap_response = result.content
        soap_response_decoded = self.with_context(efact=True)._l10n_pe_edi_decode_soap_response(soap_response) if soap_response else {}

        if soap_response_decoded.get('error'):
            return {'error': soap_response_decoded['error'], 'blocking_level': 'error',
                    'code': soap_response_decoded.get('code'), 'xml_document': edi_str}

        cdr = soap_response_decoded['cdr']
        cdr_status = self._l10n_pe_edi_extract_cdr_status(cdr)

        if cdr_status['code'] != '0':
            error_message = '%s<br/><br/><b>%s</b>' % (
                cdr_status['description'],
                _('This document number is now registered by SUNAT as invalid.')
            )
            return {'error': error_message, 'blocking_level': 'error',
                    'code': cdr_status['code'], 'xml_document': edi_str}

        return {'success': True, 'xml_document': edi_str, 'cdr': cdr}
    
    def _l10n_pe_edi_cancel_invoices_step_1_efact(self, company, invoices, void_filename, void_str):
        self.ensure_one()
        credentials = self._l10n_pe_edi_get_efact_credentials(company)
        void_tree = objectify.fromstring(void_str)
        void_tree = self._l10n_pe_sign(company.sudo().l10n_pe_edi_certificate_id, void_tree)
        void_str = etree.tostring(void_tree, xml_declaration=True, encoding='ISO-8859-1')
        zip_void_str = self._l10n_pe_edi_zip_edi_document([('%s.xml' % void_filename, void_str)])

        try:
            settings = Settings(raw_response=True)
            client = Client(
                wsdl=credentials['wsdl'],
                wsse=credentials['token'],
                settings=settings,
                operation_timeout=15,
                timeout=15,
                transport=DebugTransport(),
            )
            result = client.service.sendSummary('%s.zip' % void_filename,  zip_void_str)
            result.raise_for_status()
        except (ReqConnectionError, HTTPError, TypeError, ReadTimeout):
            return {'error': self._l10n_pe_edi_get_general_error_messages()['L10NPE08'], 'blocking_level': 'warning'}
        soap_response = result.content
        soap_response_decoded = self._l10n_pe_edi_decode_soap_response(soap_response)

        if soap_response_decoded.get('error'):
            return {'error': soap_response_decoded['error'], 'blocking_level': 'error', 'code': soap_response_decoded.get('code')}

        cdr_number = soap_response_decoded['number']
        return {'xml_document': void_str, 'cdr': soap_response, 'cdr_number': cdr_number}
    
    def _l10n_pe_edi_cancel_invoices_step_2_efact(self, company, edi_values, cdr_number):
        self.ensure_one()
        credentials = self._l10n_pe_edi_get_efact_credentials(company)
        try:
            settings = Settings(raw_response=True)
            client = Client(
                wsdl=credentials['wsdl'],
                wsse=credentials['token'],
                settings=settings,
                operation_timeout=15,
                timeout=15,
                transport=DebugTransport(),
            )
            result = client.service.getStatus(cdr_number)
            result.raise_for_status()
        except (ReqConnectionError, HTTPError, TypeError, ReadTimeout):
            return {'error': self._l10n_pe_edi_get_general_error_messages()['L10NPE08'], 'blocking_level': 'warning'}
        soap_response = result.content
        soap_response_decoded = self._l10n_pe_edi_decode_soap_response(soap_response)

        if soap_response_decoded.get('error'):
            return {'error': soap_response_decoded['error'], 'blocking_level': 'error', 'code': soap_response_decoded.get('code')}

        if not soap_response_decoded.get('cdr'):
            # The server can respond with an error code 98 which means that the cancellation has
            # not yet finished processing. In this case, the response will not contain a CDR.
            # - see https://fe-primer.greenter.dev/docs/baja#envio-a-sunat
            code = soap_response_decoded.get('code')
            error_messages_map = self._l10n_pe_edi_get_cdr_error_messages()
            error_message = '%s<br/><br/><b>%s</b>%s' % (
                error_messages_map.get(code, _("We got an error response from the OSE. ")),
                _('SOAP status code: '),
                html_escape(code),
            )
            return {'error': error_message, 'blocking_level': 'info'}

        cdr = soap_response_decoded['cdr']
        cdr_status = self._l10n_pe_edi_extract_cdr_status(cdr)

        if cdr_status['code'] != '0':
            return {'error': cdr_status['description'], 'blocking_level': 'error'}

        return {'success': True, 'cdr': cdr}
    

    def _l10n_pe_edi_get_status_cdr_efact_service(self, company, serie_folio, latam_document_type):
        credentials = self._l10n_pe_edi_get_efact_credentials(company)
        return self._l10n_pe_edi_get_status_cdr_sunat_efact(credentials, company.vat, serie_folio, latam_document_type)

    def _l10n_pe_edi_get_status_cdr_sunat_efact(self, credentials, vat_number, serie_folio, latam_document_type):
        try:
            settings = Settings(raw_response=True)
            client = Client(
                wsdl=credentials['wsdl'],
                wsse=credentials['token'],
                settings=settings,
                operation_timeout=15,
                timeout=15,
                transport=DebugTransport(),
            )
            result = client.service.getStatusCdr(vat_number, latam_document_type, serie_folio['serie'], serie_folio['folio'])
            result.raise_for_status()
        except (ReqConnectionError, HTTPError, TypeError, ReadTimeout):
            return {'error': self._l10n_pe_edi_get_general_error_messages()['L10NPE08'], 'blocking_level': 'warning'}
        soap_response = result.content
        soap_response_decoded = self._l10n_pe_edi_decode_soap_response_efact(soap_response) if soap_response else {}

        if soap_response_decoded.get('error'):
            return {'error': soap_response_decoded['error'], 'blocking_level': 'error', 'code': soap_response_decoded.get('code')}

        code = soap_response_decoded.get('code')
        status = '%s|%s' % (html_escape(code), html_escape(soap_response_decoded.get('message')))
        cdr = soap_response_decoded.get('cdr')

        return {'cdr': cdr, 'status': status, 'code': code}
    
    @api.model
    def _l10n_pe_edi_response_code_sunat(self, cdr_tree):
        """
        Efact vs SUNAT have different responses
        Example part of xml from Efact:
        <S:Body>
            <S:Fault xmlns="" xmlns:ns3="http://www.w3.org/2003/05/soap-envelope">
            <faultcode>S:Server</faultcode>
            <faultstring>1033</faultstring>
            <detail>
                <detail xmlns:SOAP-ENV="http://schemas.xmlsoap.org/soap/envelope/" xmlns:soap-env="http://schemas.xmlsoap.org/soap/envelope/">El comprobante fue registrado previamente con otros datos.</detail>
            </detail>
            </S:Fault>
        </S:Body>
        """
        if self.env.context.get('efact'):
            message_element = cdr_tree.find('.//{*}faultcode')
            if cdr_tree.find('.//{*}detail'):
                message_element = cdr_tree.find('.//{*}detail')
            if cdr_tree.find('.//{*}detail//{*}detail'):
                message_element = cdr_tree.find('.//{*}detail//{*}detail')
            code_element = cdr_tree.find('.//{*}faultstring')
            code = code_element.text
            return message_element, code
        else:
            return super()._l10n_pe_edi_response_code_sunat(cdr_tree)
        
    def _l10n_pe_edi_decode_soap_response_efact(self, soap_response):
        """
        Parse the SOAP response returned by any of the endpoints (IAP, Estela (formerly Digiflow) or SUNAT)
        for any of the SOAP operations (sendBill, getStatus, sendSummary, getStatusCdr),
        and extract, if they exist, the error, the response code, the CDR, etc.

        Returns a dict which can contain the following fields:
        'error': Description of the error (string with HTML format), if the response was a SOAP fault.
        'code': SOAP response code (a string), if one was provided.
        'message': Description of the response status (a string), if one was provided.
        'number': Ticket number (a string) returned by the getSummary endpoint.
        'cdr': the CDR (bytes with XML format), if it was provided.
        """
        try:
            response_tree = etree.fromstring(soap_response)
        except etree.LxmlError:
            return {'error': self._l10n_pe_edi_get_general_error_messages()['L10NPE08']}
        print(etree.tostring(response_tree, pretty_print=True, encoding='unicode'))
        if response_tree.find('.//{*}Fault') is not None:
            if response_tree.find('.//{*}message') is not None:  # It comes from Estela (formerly Digiflow)
                message_element, code = self._l10n_pe_edi_response_code_digiflow(response_tree)
            else:  # It comes from SUNAT
                message_element, code = self._l10n_pe_edi_decode_soap_response_efact(response_tree)
            message = message_element.text
            error_messages_map = self._l10n_pe_edi_get_cdr_error_messages()
            error_message = '%s<br/><br/><b>%s</b><br/>%s|%s' % (
                error_messages_map.get(code, _("We got an error response from the OSE. ")),
                _('Original message:'),
                html_escape(code),
                html_escape(message),
            )
            return {'error': error_message, 'code': code, 'message': message}
        if response_tree.find('.//{*}sendBillResponse') is not None:
            cdr_b64 = response_tree.find('.//{*}applicationResponse').text
            cdr = self._l10n_pe_edi_unzip_edi_document(base64.b64decode(cdr_b64))
            return {'cdr': cdr}
        if response_tree.find('.//{*}getStatusResponse') is not None:
            code = response_tree.find('.//{*}statusCode').text
            if response_tree.find('.//{*}document') is not None:
                cdr_b64 = response_tree.find('.//{*}document').text
                cdr = self._l10n_pe_edi_unzip_edi_document(base64.b64decode(cdr_b64))
            else:
                cdr = None
            return {'code': code, 'cdr': cdr}
        if response_tree.find('.//{*}sendSummaryResponse') is not None:
            ticket = response_tree.find('.//{*}ticket').text
            return {'number': ticket}
        if response_tree.find('.//{*}getStatusCdrResponse') is not None:
            code = response_tree.find('.//{*}statusCode').text if response_tree.find('.//{*}statusCode') else ''
            message = response_tree.find('.//{*}statusMessage').text if response_tree.find('.//{*}statusMessage') else ''
            if response_tree.find('.//{*}document') is not None:
                cdr_b64 = response_tree.find('.//{*}document').text
                cdr = self._l10n_pe_edi_unzip_edi_document(base64.b64decode(cdr_b64))
                return {'code': code, 'message': message, 'cdr': cdr}
            else:
                error_messages_map = self._l10n_pe_edi_get_cdr_error_messages()
                error_message = '%s<br/><br/><b>%s</b><br/>%s|%s' % (
                    error_messages_map.get(code, _("We got an error response from the OSE. ")),
                    _('Original message:'),
                    html_escape(code),
                    html_escape(message),
                )
                return {'error': error_message, 'code': code, 'message': message}
        return {'error': self._l10n_pe_edi_get_general_error_messages()['L10NPE08']}