from odoo import http, fields
from odoo.http import request
import datetime

class RollPublicController(http.Controller):

    @http.route('/rollo/datos/<int:roll_id>', type='http', auth='public', website=True)
    def roll_public_data(self, roll_id, **kwargs):
        roll = request.env['mrp.workorder.roll'].sudo().browse(roll_id)
        if not roll.exists():
            return request.not_found()
        
        company = request.env.company
        logo_url = f"{request.httprequest.host_url}web/image/res.company/{company.id}/logo/200x60"
        
        # ==== FOREACH ==== (equivalente)
        fibers_html = """
                        <table class="fibra text-start" style="width:100%; margin:auto;">
                            <thead>
                                <tr>
                                    <th>Fibra</th>
                                    <th>%</th>
                                    <th>Lote</th>
                                </tr>
                            </thead>
                            <tbody>
                    """
        
        # Construcción condicional del bloque de opción
        option_html = ""
        if roll.option_id:
            option_html = f"""
                <div class="row">
                    <span class="label">Opción:</span>
                    <span class="value">{roll.option_id.name}</span>
                </div>"""
            if roll.option_id.notes:
                option_html += f"""
                <div class="row">
                    <span class="label">Observación:</span>
                    <span class="value">{roll.option_id.notes}</span>
                </div>"""
        color_html = ""
        if roll.workorder_id.production_id.color_recipe_id and roll.workorder_id.production_id.color_recipe_id.state == 'approved':
            color_html = f"""
                <div class="row">
                    <span class="label">Color:</span>
                    <span class="value">[{roll.workorder_id.production_id.color_recipe_id.color_code}] {roll.workorder_id.production_id.color_recipe_id.color_name}</span>
                </div>"""
        else:
            color_html = f"""
                <div class="row">
                    <span class="label">Color:</span>
                    <span class="value">{roll.workorder_id.production_id.sale_order_line_id.product_color_id.name}</span>
                </div>"""
        technical_sheet_id = roll.workorder_id.production_id.bom_id.technical_sheet_id
        weaving_data_id = roll.workorder_id.product_id.product_tmpl_id.analysis_id.weaving_data_ids.filtered(lambda w: w.technical_sheet_id == technical_sheet_id)
        for fiber in weaving_data_id.fiber_ids:
            fibers_html += f"""
                                <tr>
                                    <td>{fiber.product_template_id.name or ''}</td>
                                    <td>{(fiber.percentage or 0) * 100:.2f} %</td>
                                    <td>{roll.option_id.option_line_ids.filtered(lambda l: l.product_id.product_tmpl_id == fiber.product_template_id).mapped('lot_id').name if roll.option_id else roll.workorder_id.production_id.move_raw_ids.filtered(lambda l: l.product_id.product_tmpl_id == fiber.product_template_id).move_line_ids.mapped('lot_id')[0].name}</td>
                                </tr>
                            """
            
        fibers_html += """
                                </tbody>
                            </table>
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

                /* --- bordes para la tabla --- */
                table.fibra {{
                    width: 100%;
                    border-collapse: collapse;   /* junta los bordes */
                    margin: auto;
                }}
                table.fibra td:nth-child(2) {{
                    white-space: nowrap;
                }}
                table.fibra td:nth-child(3) {{
                    white-space: nowrap;
                }}
                table.fibra th, table.fibra td {{
                    text-align: left !important;
                    border: 1px solid #ccc;
                    padding: 4px 6px;
                }}
                table.fibra thead {{
                    background: #f0f0f0;
                }}
            </style>
        </head>
        <body>
            <div class="card">
                <div class="header">
                    <img src="{logo_url}" alt="Logo" style="max-height: 60px;">
                </div>
                <h1 class="title">Información del rollo</h1>
                <div class="row">
                    <span class="label">Fecha y Hora:</span>
                    <span class="value">{fields.Datetime.context_timestamp(request.env.user, roll.create_date).strftime("%d/%m/%Y %H:%M")}</span>
                </div>
                <div class="row">
                    <span class="label">Número:</span>
                    <span class="value">{roll.name or ''}</span>
                </div>
                <div class="row">
                    <span class="label">Peso Tejido(kg):</span>
                    <span class="value">{(roll.gross_weight or 0):.2f}</span>
                </div>
                <div class="row">
                    <span class="label">Peso Neto (kg):</span>
                    <span class="value">{(roll.net_weight or 0):.2f}</span>
                </div>
                <div class="row">
                    <span class="label">Proceso:</span>
                    <span class="value">{roll.workorder_id.name or ''}</span>
                </div>
                <div class="row">
                    <span class="label">Cliente:</span>
                    <span class="value">{roll.workorder_id.production_id.sale_order_line_id.order_id.partner_id.name or roll.workorder_id.company_id.partner_id.name}</span>
                </div>
                <div class="row">
                    <span class="label">Orden de Producción:</span>
                    <span class="value">{roll.workorder_id.production_id.name or ''}</span>
                </div>
                <div class="row">
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
                {color_html}
                <div class="row">
                    <span class="label">Inicio:</span>
                    <span class="value">{roll.roll_start}</span>
                </div>
                <div class="row">
                    <span class="label">Fin:</span>
                    <span class="value">{roll.roll_end}</span>
                </div>
                {option_html}
            </div>
        </body>
        </html>
        """
        return html
    
    @http.route('/rollo/datos/<string:name>', type='http', auth='public', website=True)
    def roll_public_by_name_data(self, name, **kwargs):
        roll = request.env['mrp.workorder.roll'].sudo().search([('name', '=', name)], limit=1)
        if not roll.exists():
            return request.not_found()
        return self.roll_public_data(roll.id)