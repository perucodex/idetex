from odoo import http
from odoo.http import request

class RollPublicController(http.Controller):

    @http.route('/rollo/<int:roll_id>/datos', type='http', auth='public', website=True)
    def roll_public_data(self, roll_id, **kwargs):
        roll = request.env['mrp.workorder.roll'].sudo().browse(roll_id)
        if not roll.exists():
            return request.not_found()

        html = f"""
        <!DOCTYPE html>
        <html lang="es">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <title>Información del rollo</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 0; padding: 20px; background: #f5f5f5; }}
                .card {{ background: #fff; border-radius: 8px; padding: 20px; max-width: 400px; margin: auto; box-shadow: 0 2px 8px rgba(0,0,0,.1); }}
                .title {{ text-align: center; margin-bottom: 20px; color: #333; }}
                .row {{ display: flex; justify-content: space-between; margin-bottom: 12px; }}
                .label {{ font-weight: 600; color: #555; }}
                .value {{ color: #222; }}
            </style>
        </head>
        <body>
            <div class="card">
                <h1 class="title">Información del rollo</h1>
                <div class="row">
                    <span class="label">Número:</span>
                    <span class="value">{roll.name or ''}</span>
                </div>
                <div class="row">
                    <span class="label">Peso (kg):</span>
                    <span class="value">{roll.gross_weight or ''}</span>
                </div>
                <div class="row">
                    <span class="label">Ancho (m):</span>
                    <span class="value">{roll.net_weight or ''}</span>
                </div>
                <div class="row">
                    <span class="label">Largo (m):</span>
                    <span class="value">{roll.workorder_id.name or ''}</span>
                </div>
            </div>
        </body>
        </html>
        """
        return html