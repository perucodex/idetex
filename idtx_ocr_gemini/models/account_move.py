"""Override _contact_iap_extract para facturas via Gemini. Incluye el
post-OCR fill estandar (l10n_pe SUNAT, partner por RUC, descripcion,
recomposicion del name).
"""
import logging

from odoo import api, models

from .extract_mixin import PROMPT_INVOICE, gemini_invoice_to_iap

_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    _inherit = 'account.move'

    def _get_import_file_type(self, file_data):
        name = (file_data.get('name') or '').lower()
        mt = (file_data.get('mimetype') or '').lower()
        if 'webp' in mt or name.endswith('.webp'):
            return 'png'
        if 'tiff' in mt or name.endswith(('.tif', '.tiff')):
            return 'png'
        if 'bmp' in mt or name.endswith('.bmp'):
            return 'png'
        if 'gif' in mt or name.endswith('.gif'):
            return 'png'
        return super()._get_import_file_type(file_data)

    @api.model
    def _contact_iap_extract(self, pathinfo, params):
        if pathinfo == 'parse':
            return self._idtx_gemini_run(
                params, PROMPT_INVOICE, gemini_invoice_to_iap,
            )
        if pathinfo == 'get_result':
            return self._idtx_gemini_get_result(params)
        if pathinfo == 'validate':
            return {'status': 'success'}
        return {'status': 'error_internal'}

    def _fill_document_with_results(self, ocr_results):
        super()._fill_document_with_results(ocr_results)
        if not ocr_results:
            return

        # 1. Numero SUNAT + tipo de documento
        if 'l10n_latam_document_number' in self._fields:
            invoice_id = self._get_ocr_selected_value(ocr_results, 'invoice_id', None)
            if invoice_id:
                latam_num = invoice_id
                prefix = None
                if len(latam_num) > 1 and latam_num[0].isalpha() and latam_num[1].isdigit():
                    prefix = latam_num[0].upper()
                    latam_num = latam_num[1:]
                if self.l10n_latam_document_number != latam_num:
                    self.l10n_latam_document_number = latam_num
                if prefix and 'l10n_latam_document_type_id' in self._fields:
                    doc_type = self._pc_match_latam_document_type(prefix)
                    if doc_type and self.l10n_latam_document_type_id != doc_type:
                        self.l10n_latam_document_type_id = doc_type
                if prefix:
                    expected_name = "%s %s" % (prefix, latam_num)
                    if self.name != expected_name:
                        self.name = expected_name
                _logger.info(
                    "idtx_ocr_gemini: l10n_latam_document_number=%s (raw=%s) en move id=%s",
                    latam_num, invoice_id, self.id,
                )

        # 2. Partner por RUC
        vat = (self._get_ocr_selected_value(ocr_results, 'VAT_Number', None) or '').strip()
        if vat and not self.partner_id:
            partner = self._pc_find_or_create_partner_by_vat(vat)
            if partner:
                self.partner_id = partner

        # 3. Descripcion del producto + price_unit fallback
        product_desc = self._get_ocr_selected_value(ocr_results, 'product_description', None)
        product_lines = self.invoice_line_ids.filtered(
            lambda l: l.display_type not in ('line_section', 'line_note')
        )
        if product_desc and product_lines:
            product_lines[0].name = product_desc
        if product_lines and all(not l.price_unit for l in product_lines):
            total = self._get_ocr_selected_value(ocr_results, 'total', None)
            try:
                total = float(total) if total is not None else None
            except (TypeError, ValueError):
                total = None
            if total:
                product_lines[0].quantity = 1.0
                product_lines[0].price_unit = total

    _PC_LATAM_DOC_TYPE_BY_PREFIX = {'F': '01', 'B': '03'}

    def _pc_match_latam_document_type(self, prefix):
        code = self._PC_LATAM_DOC_TYPE_BY_PREFIX.get(prefix)
        if not code:
            return False
        DocType = self.env['l10n_latam.document.type'].sudo()
        pe_country = self.env.ref('base.pe', raise_if_not_found=False)
        domain = [('code', '=', code)]
        if pe_country:
            domain.append(('country_id', '=', pe_country.id))
        return DocType.search(domain, limit=1)

    def _pc_find_or_create_partner_by_vat(self, vat):
        if not vat:
            return False
        Partner = self.env['res.partner'].sudo()
        partner = Partner.search([('vat', '=', vat)], limit=1)
        if partner:
            return partner
        IdentType = self.env['l10n_latam.identification.type'].sudo()
        ruc_type = IdentType.search([('l10n_pe_vat_code', '=', '6')], limit=1)
        if not ruc_type or not hasattr(Partner, 'ConsultarRUC'):
            return Partner.create({
                'name': vat,
                'vat': vat,
                'l10n_latam_identification_type_id': ruc_type.id if ruc_type else False,
                'is_company': True,
            })
        partner = Partner.create({
            'name': vat,
            'vat': vat,
            'l10n_latam_identification_type_id': ruc_type.id,
            'is_company': True,
        })
        try:
            partner.ConsultarRUC(vat)
        except Exception:
            _logger.warning(
                "idtx_ocr_gemini: ConsultarRUC fallo para %s — partner basico",
                vat, exc_info=True,
            )
        return partner
