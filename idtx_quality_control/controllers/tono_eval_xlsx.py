from odoo import http
from odoo.http import content_disposition, request


class TonoEvalXlsxController(http.Controller):

    @http.route('/idtx_quality_control/tono_eval_xlsx', type='http', auth='user')
    def tono_eval_xlsx(self, ids='', company_id='', **kwargs):
        """Descarga el formato 'Evaluación de Tono en Producción' en Excel.
        Los ACL/reglas del modelo aplican con el usuario de la sesión.
        company_id = compañía activa del cliente web (el GET no la hereda),
        para que el logo/nombre del formato sea el mismo que en el PDF."""
        log_ids = [int(i) for i in ids.split(',') if i.strip().isdigit()]
        logs = request.env['qc.tone.eval.log'].browse(log_ids).exists()
        if not logs:
            return request.not_found()
        cid = int(company_id) if str(company_id).isdigit() else 0
        if cid and cid in request.env.user.company_ids.ids:
            logs = logs.with_company(cid)
        data = logs._build_tono_eval_xlsx()
        filename = 'Evaluacion de Tono en Produccion.xlsx'
        return request.make_response(data, headers=[
            ('Content-Type', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'),
            ('Content-Length', len(data)),
            ('Content-Disposition', content_disposition(filename)),
        ])
