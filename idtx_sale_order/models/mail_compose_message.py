import base64
from odoo import api, models

class MailComposeMessage(models.TransientModel):
    _inherit = 'mail.compose.message'

    @api.depends('composition_mode', 'model', 'res_domain', 'res_ids', 'template_id')
    def _compute_attachment_ids(self):
        super()._compute_attachment_ids()
        for composer in self:
            sheet_ids = composer.env.context.get('technical_sheet_ids_to_attach')
            if not sheet_ids:
                continue
            if composer.model != 'sale.order' or composer.composition_mode != 'comment':
                continue
            if composer.composition_batch:
                continue
            sheets = composer.env['technical.sheet'].browse(sheet_ids).exists()
            if not sheets:
                continue
            # report = composer.env.ref('idtx_product_development.action_report_technical_sheet')
            existing = composer.attachment_ids
            new_attachments = composer.env['ir.attachment']
            for sheet in sheets:
                filename = f"Technical Sheet - {sheet.product_code}.pdf"
                if existing.filtered(lambda a: a.name == filename):
                    continue
                pdf_content, _ = composer.env['ir.actions.report']._render_qweb_pdf('idtx_sale_order.action_report_technical_sheet_customer', res_ids=[sheet.id])
                new_attachments += composer.env['ir.attachment'].create({
                    'name': filename,
                    'type': 'binary',
                    'datas': base64.b64encode(pdf_content),
                    'mimetype': 'application/pdf',
                    'res_model': 'mail.compose.message',
                    'res_id': 0,
                })
            if new_attachments:
                composer.attachment_ids = existing | new_attachments
