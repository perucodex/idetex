# -*- coding: utf-8 -*-

import base64
import io
import zipfile
from odoo import models, api

class AccountMoveSend(models.AbstractModel):
    _inherit = 'account.move.send'

    def _get_invoice_extra_attachments(self, move):
        result = super()._get_invoice_extra_attachments(move)
        if move.company_id.account_fiscal_country_id.code == 'PE':
            zip_attachments = result.filtered(lambda a: a.name.endswith('.zip'))
            for zip_att in zip_attachments:
                try:
                    zip_data = base64.b64decode(zip_att.datas)
                    with zipfile.ZipFile(io.BytesIO(zip_data)) as z:
                        for zname in z.namelist():
                            if not (zname.endswith('.xml') or zname.endswith('.XML')):
                                continue
                            
                            existing = self.env['ir.attachment'].search([
                                ('res_model', '=', 'account.move'),
                                ('res_id', '=', move.id),
                                ('name', '=', zname)
                            ], limit=1)
                            
                            if not existing:
                                zcontent = z.read(zname)
                                existing = self.env['ir.attachment'].create({
                                    'name': zname,
                                    'type': 'binary',
                                    'datas': base64.b64encode(zcontent),
                                    'mimetype': 'application/xml',
                                    'res_model': 'account.move',
                                    'res_id': move.id,
                                })
                            result += existing
                    result -= zip_att
                except Exception:
                    pass
        if move.company_id.account_fiscal_country_id.code == 'PE' and move.state == 'cancel':
            void_attachments = self.env['ir.attachment'].search([
                ('res_model', '=', 'account.move'),
                ('res_id', '=', move.id),
                ('name', 'ilike', 'VOID-')
            ])
            result |= void_attachments
            chatter_attachments = move.message_ids.attachment_ids.filtered(
                lambda a: a.name and 'VOID-' in a.name.upper()
            )
            result |= chatter_attachments
        
        # Deduplicate attachments by name
        seen_names = set()
        deduplicated_result = self.env['ir.attachment']
        for attachment in result:
            if attachment.name not in seen_names:
                seen_names.add(attachment.name)
                deduplicated_result |= attachment
        return deduplicated_result

    @api.model
    def _get_move_constraints(self, move):
        constraints = super()._get_move_constraints(move)
        if move.state == 'cancel' and move.is_sale_document(include_receipts=True):
            constraints.pop('not_posted', None)
        return constraints

    @api.model
    def _get_default_mail_subject(self, move, mail_template, mail_lang):
        if move.company_id.account_fiscal_country_id.code == 'PE' and move.state == 'cancel' and move.is_sale_document():
            doc_type_name = "Factura"
            if move.l10n_latam_document_type_id:
                doc_name = move.l10n_latam_document_type_id.name
                if "boleta" in doc_name.lower():
                    doc_type_name = "Boleta"
                elif "nota de crédito" in doc_name.lower():
                    doc_type_name = "Nota de Crédito"
                elif "nota de débito" in doc_name.lower():
                    doc_type_name = "Nota de Débito"
            company_name = move.company_id.name or "IDETEX S.A.C."
            return f"{company_name} ha dado de Baja o Revertido un(a) {doc_type_name} (Ref {move.name})"
        return super()._get_default_mail_subject(move, mail_template, mail_lang)
