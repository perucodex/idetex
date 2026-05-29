"""Wizard que pide la contrasena de un PDF protegido antes de mandarlo
a Gemini. Misma logica que en otros modulos OCR.
"""
import io
import logging

from odoo import _, fields, models
from odoo.exceptions import UserError


_logger = logging.getLogger(__name__)


def _normalize_pdf_bytes(raw):
    if not raw:
        return None
    idx = raw[:32].find(b'%PDF')
    if idx < 0:
        return None
    return raw[idx:] if idx > 0 else raw


def _is_pdf_encrypted(raw_bytes):
    pdf_bytes = _normalize_pdf_bytes(raw_bytes)
    if pdf_bytes is None:
        return False
    try:
        from pypdf import PdfReader
    except ImportError:
        try:
            from PyPDF2 import PdfFileReader as PdfReader
        except ImportError:
            _logger.warning("pypdf/PyPDF2 no disponibles — no se detectaran PDFs encriptados")
            return False
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes), strict=False)
        return bool(getattr(reader, 'is_encrypted', False) or getattr(reader, 'isEncrypted', False))
    except Exception:
        _logger.warning("Error leyendo PDF para deteccion de encripcion", exc_info=True)
        return False


def _decrypt_pdf(raw_bytes, password):
    pdf_bytes = _normalize_pdf_bytes(raw_bytes) or raw_bytes
    try:
        from pypdf import PdfReader, PdfWriter
        legacy = False
    except ImportError:
        from PyPDF2 import PdfFileReader as PdfReader, PdfFileWriter as PdfWriter
        legacy = True
    reader = PdfReader(io.BytesIO(pdf_bytes), strict=False)
    is_enc = getattr(reader, 'is_encrypted', False) or getattr(reader, 'isEncrypted', False)
    if not is_enc:
        return raw_bytes
    if not reader.decrypt(password or ''):
        raise UserError(_("Contrasena incorrecta para el PDF."))
    writer = PdfWriter()
    if legacy:
        for i in range(reader.getNumPages()):
            writer.addPage(reader.getPage(i))
    else:
        for page in reader.pages:
            writer.add_page(page)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


class PdfPasswordWizard(models.TransientModel):
    _name = 'idtx_ocr_gemini.pdf_password_wizard'
    _description = 'Wizard para desbloquear PDFs antes de mandarlos a Gemini'

    journal_id = fields.Many2one(
        'account.journal',
        required=True,
        ondelete='cascade',
    )
    attachment_ids = fields.Many2many(
        'ir.attachment',
        'idtx_ocr_gemini_pdf_wiz_att_rel',
        'wizard_id',
        'attachment_id',
        string='PDFs protegidos',
        required=True,
    )
    other_attachment_ids = fields.Many2many(
        'ir.attachment',
        'idtx_ocr_gemini_pdf_wiz_other_rel',
        'wizard_id',
        'attachment_id',
        string='Otros archivos (no encriptados)',
    )
    password = fields.Char(
        string='Contrasena',
        help='Contrasena para desencriptar los PDFs listados. No se guarda.',
    )

    def action_unlock_and_import(self):
        self.ensure_one()
        if not self.password:
            raise UserError(_("Ingresa la contrasena del PDF."))
        for att in self.attachment_ids:
            decrypted = _decrypt_pdf(att.raw or b'', self.password)
            att.write({'raw': decrypted})
        all_attachments = self.attachment_ids | self.other_attachment_ids
        return self.journal_id.with_context(
            idtx_ocr_gemini_pdf_unlocked=True,
        )._import_bank_statement(all_attachments)
