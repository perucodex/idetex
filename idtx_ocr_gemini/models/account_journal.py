from odoo import _, models


class AccountJournal(models.Model):
    _inherit = 'account.journal'

    def _is_attachment_ocrizable(self, attachment):
        """Acepta PDF, WebP, TIFF, BMP, GIF ademas de los jpg/png que
        Odoo enterprise declara. Gemini maneja todos via inline_data.
        """
        if super()._is_attachment_ocrizable(attachment):
            return True
        mt = (attachment.mimetype or '').lower()
        name = (attachment.name or '').lower()
        if 'pdf' in mt or name.endswith('.pdf'):
            return True
        if 'webp' in mt or name.endswith('.webp'):
            return True
        if 'tiff' in mt or name.endswith(('.tif', '.tiff')):
            return True
        if 'bmp' in mt or name.endswith('.bmp'):
            return True
        if 'gif' in mt or name.endswith('.gif'):
            return True
        return False

    def _import_bank_statement(self, attachments):
        """Detecta PDFs encriptados antes del flujo normal y abre wizard."""
        if not self.env.context.get('idtx_ocr_gemini_pdf_unlocked'):
            from ..wizards.pdf_password_wizard import _is_pdf_encrypted
            encrypted = self.env['ir.attachment']
            others = self.env['ir.attachment']
            for att in attachments:
                if _is_pdf_encrypted(att.raw or b''):
                    encrypted |= att
                else:
                    others |= att
            if encrypted:
                wizard = self.env['idtx_ocr_gemini.pdf_password_wizard'].create({
                    'journal_id': self.id,
                    'attachment_ids': [(6, 0, encrypted.ids)],
                    'other_attachment_ids': [(6, 0, others.ids)],
                })
                view = self.env.ref(
                    'idtx_ocr_gemini.pdf_password_wizard_form'
                )
                return {
                    'type': 'ir.actions.act_window',
                    'res_model': 'idtx_ocr_gemini.pdf_password_wizard',
                    'views': [(view.id, 'form')],
                    'view_mode': 'form',
                    'res_id': wizard.id,
                    'target': 'new',
                    'name': _('PDF protegido con contrasena'),
                }
        return super()._import_bank_statement(attachments)
