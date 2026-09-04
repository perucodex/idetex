from odoo import http
from odoo.http import request
from datetime import datetime


class LaboratorioPublicController(http.Controller):

    @http.route('/qc/lab/<int:line_id>', type='http', auth='public')
    def laboratorio_resultado_publico(self, line_id, access_token=None, **kwargs):
        line = request.env['mrp.workorder.batch'].sudo().browse(line_id)
        if not line.exists():
            return request.not_found()
        if not access_token or access_token != line.lab_public_token:
            return request.not_found()

        recipient = line._get_mail_recipient_partner()
        lang = kwargs.get('lang') or (recipient.lang if recipient else False) or 'en_US'
        request.update_context(lang=lang)

        line = line.with_context(lang=lang)
        payload = line._laboratorio_summary_report_payload()
        values = {
            'line': line,
            'payload': payload,
            'company': request.env.company,
            'base_url': request.env['ir.config_parameter'].sudo().get_param('web.base.url') or '',
            'print_date': datetime.now().strftime('%d/%m/%Y'),
        }
        return request.render('idtx_quality_control.laboratorio_resultado_publico_page', values)
