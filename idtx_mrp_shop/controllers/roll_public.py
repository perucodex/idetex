from odoo import http
from odoo.http import request

class RollPublicController(http.Controller):

    @http.route('/rollo/<int:roll_id>/datos', type='http', auth='public', website=True)
    def roll_public_data(self, roll_id, **kwargs):
        roll = request.env['mrp.workorder.roll'].sudo().browse(roll_id)
        if not roll.exists():
            return request.not_found()
        
        company = request.env.company
        logo_url = f"{request.httprequest.host_url}web/image/res.company/{company.id}/logo/200x60"
        
        # ==== FOREACH ==== (equivalente)
        fibers_html = ""
        technical_sheet_id = roll.workorder_id.production_id.bom_id.technical_sheet_id
        weaving_data_id = roll.workorder_id.product_id.product_tmpl_id.analysis_id.weaving_data_ids.filtered(lambda w: w.technical_sheet_id == technical_sheet_id)
        for fiber in weaving_data_id.fiber_ids:
            fibers_html += f"""
            <div class="col-6 col-md-3 mb-3 text-center">
                <span>{fiber.product_template_id.name or ''}</span> <span>{round((fiber.percentage or 0) * 100, 2)} %</span><br/>
            </div>
            """

        html = f"""
        <!DOCTYPE html>
        <html lang="es">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <title>Información del rollo</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 0; padding: 20px; background: #f5f5f5; }}
                .header{{ text-align: center;}}
                .card {{ background: #fff; border-radius: 8px; padding: 20px; max-width: 400px; margin: auto; box-shadow: 0 2px 8px rgba(0,0,0,.1); }}
                .title {{ text-align: center; margin-bottom: 20px; color: #333; }}
                .row {{ display: flex; justify-content: space-between; margin-bottom: 12px; }}
                .label {{ font-weight: 600; color: #555; }}
                .value {{ color: #222; }}
            </style>
        </head>
        <body>
            <div class="card">
                <div class="header">
                    <img src="{logo_url}" alt="Logo" style="max-height: 60px;">
                </div>
                <h1 class="title">Información del rollo</h1>
                <div class="row">
                    <span class="label">Número:</span>
                    <span class="value">{roll.name or ''}</span>
                </div>
                <div class="row">
                    <span class="label">Peso Tejido(kg):</span>
                    <span class="value">{roll.gross_weight or ''}</span>
                </div>
                <div class="row">
                    <span class="label">Peso Neto (kg):</span>
                    <span class="value">{roll.net_weight or ''}</span>
                </div>
                <div class="row">
                    <span class="label">Proceso:</span>
                    <span class="value">{roll.workorder_id.name or ''}</span>
                </div>
                <div class="row">
                    <span class="label">Cliente:</span>
                    <span class="value">{roll.workorder_id.production_id.sale_order_line_id.order_id.partner_id.name or ''}</span>
                </div>
                <div class="row">
                    <span class="label">Orden de Producción:</span>
                    <span class="value">{roll.workorder_id.production_id.name or ''}</span>
                </div>
                <div class="row">
                    <span class="label">Fibras:</span>
                    <span class="value">{fibers_html}</span>
                </div>
                <div class="row">
                    <span class="label">Maquina:</span>
                    <span class="value">{roll.equipment_id.name}</span>
                </div>
                <div class="row">
                    <span class="label">Tejedor:</span>
                    <span class="value">{roll.employee_id.name}</span>
                </div>
                <div class="row">
                    <span class="label">Color:</span>
                    <span class="value">[{roll.workorder_id.production_id.color_recipe_id.color_code}] {roll.workorder_id.production_id.color_recipe_id.color_name}</span>
                </div>
            </div>
        </body>
        </html>
        """
        return html