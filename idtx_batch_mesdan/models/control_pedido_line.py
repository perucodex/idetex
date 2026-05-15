# -*- coding: utf-8 -*-
import base64
import io
from ftplib import FTP, error_perm

from odoo import _, fields, models
from odoo.exceptions import UserError

FTP_HOST = "172.16.64.100"
FTP_USER = "Mesdan"
FTP_PASS_B64 = "TWVzZGFu"
FTP_REPORTS_DIR = "/mnt/Part2/Reports"


class ControlPedidoLine(models.Model):
    _inherit = "control.pedido.line"

    report_pdf_attached = fields.Boolean(compute='_compute_report_pdf_attached')

    def _compute_report_pdf_attached(self):
        Attachment = self.env['ir.attachment']
        for rec in self:
            if not rec.id:
                rec.report_pdf_attached = False
                continue
            rec.report_pdf_attached = bool(Attachment.search_count([
                ('res_model', '=', rec._name),
                ('res_id', '=', rec.id),
                ('name', 'like', 'Rep_None_%'),
                ('mimetype', '=', 'application/pdf'),
            ], limit=1))

    def _ftp_find_report_pdf(self, ftp, batch):
        """Return (filename, folder, content_bytes) for the most recent report PDF matching `batch`."""
        ftp.cwd(FTP_REPORTS_DIR)

        # YY_MM_DD folders are lexicographically sortable; descending = newest first
        folders = sorted(
            (n for n in ftp.nlst() if len(n) == 8 and n[2] == '_' and n[5] == '_'),
            reverse=True,
        )
        if not folders:
            raise UserError(_("No hay carpetas de reportes en %s.") % FTP_REPORTS_DIR)

        clean_batch = batch[1:] if batch.startswith('C') else batch

        for folder in folders:
            try:
                ftp.cwd(folder)
            except error_perm:
                continue
            try:
                candidates = [
                    name for name in ftp.nlst()
                    if name.lower().endswith(".pdf")
                    and (f"_C{clean_batch}_" in name or f"_{clean_batch}_" in name)
                ]
                if candidates:
                    filename = sorted(candidates)[-1]
                    buf = io.BytesIO()
                    ftp.retrbinary(f"RETR {filename}", buf.write)
                    return filename, folder, buf.getvalue()
            finally:
                ftp.cwd("..")

        raise UserError(_("No se encontró un PDF para la partida %s en ninguna carpeta de reportes.") % batch)

    def action_fetch_report_pdf(self):
        self.ensure_one()
        if not self.batch:
            raise UserError(_("Esta línea no tiene partida."))

        password = base64.b64decode(FTP_PASS_B64).decode("utf-8")
        ftp = FTP(FTP_HOST, timeout=30)
        try:
            ftp.login(FTP_USER, password)
            filename, folder, content = self._ftp_find_report_pdf(ftp, self.batch)

            attachment = self.env['ir.attachment'].create({
                'name': filename,
                'datas': base64.b64encode(content),
                'res_model': self._name,
                'res_id': self.id,
                'mimetype': 'application/pdf',
            })
            self.message_post(
                body=_("Reporte importado desde FTP (%s): %s") % (folder, filename),
                attachment_ids=[attachment.id],
            )

            # Remove the report from the FTP only after it is safely stored in
            # Odoo. _ftp_find_report_pdf leaves the cwd at FTP_REPORTS_DIR.
            try:
                ftp.delete(f"{folder}/{filename}")
            except Exception:
                # The PDF is already attached; a failed cleanup must not abort.
                self.message_post(body=_(
                    "No se pudo borrar %s del FTP; eliminarlo manualmente."
                ) % filename)
        finally:
            try:
                ftp.quit()
            except Exception:
                ftp.close()
        return True
