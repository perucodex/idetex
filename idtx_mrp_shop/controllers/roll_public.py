from odoo import http, fields
from odoo.http import request
from markupsafe import escape
import datetime


class RollPublicController(http.Controller):

    @http.route('/rollo/datos/<int:roll_id>', type='http', auth='public', website=True)
    def roll_public_data(self, roll_id, **kwargs):
        roll = request.env['mrp.workorder.roll'].sudo().browse(roll_id)
        if not roll.exists():
            return request.not_found()

        company = request.env.company
        logo_url = f"{request.httprequest.host_url}web/image/res.company/{company.id}/logo/200x60"

        # ¿Usuario INTERNO? Solo ellos ven los enlaces a los registros del
        # backend; un usuario externo/público ve la data pero sin enlaces.
        is_internal = request.env.user.has_group('base.group_user')

        def backend_link(model, rid, text):
            """Enlace al registro en el backend (solo usuarios internos)."""
            text = escape(text or '')
            if is_internal and rid:
                return (f'<a href="/web#id={rid}&model={model}&view_type=form" '
                        f'target="_blank">{text}</a>')
            return text

        def fmt_dt(dt):
            if not dt:
                return ''
            return fields.Datetime.context_timestamp(
                request.env.user, dt).strftime("%d/%m/%Y %H:%M")

        # ==== Tabla de fibras (pestaña Tejido) ====
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

        option_html = ""
        if roll.option_id:
            option_html = f"""
                <div class="row">
                    <span class="label">Opción:</span>
                    <span class="value">{escape(roll.option_id.name or '')}</span>
                </div>"""
            if roll.option_id.notes:
                option_html += f"""
                <div class="row">
                    <span class="label">Observación:</span>
                    <span class="value">{escape(roll.option_id.notes or '')}</span>
                </div>"""
        color_html = ""
        if roll.workorder_id.production_id.color_recipe_id and roll.workorder_id.production_id.color_recipe_id.state == 'approved':
            color_html = f"""
                <div class="row">
                    <span class="label">Color:</span>
                    <span class="value">[{escape(roll.workorder_id.production_id.color_recipe_id.color_code or '')}] {escape(roll.workorder_id.production_id.color_recipe_id.color_name or '')}</span>
                </div>"""
        else:
            color_html = f"""
                <div class="row">
                    <span class="label">Color:</span>
                    <span class="value">{escape(roll.workorder_id.production_id.sale_order_line_id.product_color_id.name or '')}</span>
                </div>"""
        technical_sheet_id = roll.workorder_id.production_id.bom_id.technical_sheet_id
        weaving_data_id = roll.workorder_id.product_id.product_tmpl_id.analysis_id.weaving_data_ids.filtered(lambda w: w.technical_sheet_id == technical_sheet_id)
        for fiber in weaving_data_id.fiber_ids if roll.workorder_id.production_id.state != 'cancel' else []:
            lot_name = ''
            try:
                if roll.option_id:
                    lot_name = roll.option_id.option_line_ids.filtered(
                        lambda l: l.product_id.product_tmpl_id == fiber.product_template_id
                    ).mapped('lot_id').name or ''
                else:
                    lots = roll.workorder_id.production_id.move_raw_ids.filtered(
                        lambda l: l.product_id.product_tmpl_id == fiber.product_template_id
                    ).move_line_ids.mapped('lot_id')
                    lot_name = lots[0].name if lots else ''
            except Exception:
                lot_name = ''
            fibers_html += f"""
                                <tr>
                                    <td>{escape(fiber.product_template_id.name or '')}</td>
                                    <td>{(fiber.percentage or 0) * 100:.2f} %</td>
                                    <td>{escape(lot_name or 'False')}</td>
                                </tr>
                            """
        fibers_html += """
                                </tbody>
                            </table>
                        """

        # ==== OF como enlace ====
        production = roll.workorder_id.production_id
        of_html = backend_link('mrp.production', production.id, production.name or '')

        # ==== Registros de teñido / acabado (batch.registry) ====
        # El rollo pertenece a una partida (y a sus ancestros, por las
        # divisiones): sus registros de operación viven en ese linaje.
        Batch = request.env['mrp.workorder.batch'].sudo()
        batches = Batch.search([('wo_roll_ids', 'in', roll.id)])
        lineage = batches
        node = batches
        seen = Batch.browse()
        while node:
            seen |= node
            node = node.parent_batch_id - seen
            lineage |= node
        registries = lineage.registry_ids
        sentinel = datetime.datetime(1900, 1, 1)

        def by_type(op_type):
            return registries.filtered(
                lambda r: r.workorder_id.operation_type == op_type).sorted(
                key=lambda r: (r.registry_date or sentinel, r.id))

        dyeing_regs = by_type('dyeing')
        finishing_regs = by_type('finishing')
        printing_regs = by_type('printing')
        quality_regs = by_type('quality')
        # La pestaña Estampado solo aparece si la OF tiene alguna OT en printing
        # (o si hay registros de estampado en el linaje de la partida).
        has_printing = bool(production.workorder_ids.filtered(
            lambda w: w.operation_type == 'printing')) or bool(printing_regs)

        state_labels = {'draft': 'Borrador', 'done': 'Hecho', 'rejected': 'Rechazado'}

        def registry_table(regs, empty_msg):
            if not regs:
                return f'<p class="empty">{escape(empty_msg)}</p>'
            ver_th = '<th>Ver</th>' if is_internal else ''
            rows = ""
            for r in regs:
                op = r.workorder_id.mrwo_id.name or r.workorder_id.name or ''
                ver_td = ''
                if is_internal:
                    ver_td = f'<td>{backend_link("batch.registry", r.id, "Abrir")}</td>'
                rows += f"""
                    <tr>
                        <td>{escape(fmt_dt(r.registry_date))}</td>
                        <td>{escape(op)}</td>
                        <td style="text-align:center">{r.reprocess_number}</td>
                        <td>{escape(r.employee_id.name or '')}</td>
                        <td>{escape(r.equipment_id.name or '')}</td>
                        <td>{escape(r.color_name or '')}</td>
                        <td>{escape(state_labels.get(r.state, r.state or ''))}</td>
                        {ver_td}
                    </tr>"""
            return f"""
                <table class="reg">
                    <thead>
                        <tr>
                            <th>Fecha</th>
                            <th>Operación</th>
                            <th>N°</th>
                            <th>Empleado</th>
                            <th>Equipo</th>
                            <th>Color</th>
                            <th>Estado</th>
                            {ver_th}
                        </tr>
                    </thead>
                    <tbody>{rows}</tbody>
                </table>"""

        tintoreria_html = registry_table(dyeing_regs, 'Sin registros de tintorería para este rollo.')
        acabado_html = registry_table(finishing_regs, 'Sin registros de acabado para este rollo.')
        estampado_html = registry_table(printing_regs, 'Sin registros de estampado para este rollo.')
        calidad_html = registry_table(quality_regs, 'Sin registros de calidad para este rollo.')

        estampado_tab = ('<button class="tab" onclick="showTab(\'estampado\', this)">'
                         'Estampado</button>') if has_printing else ''
        estampado_pane = (f'<div id="estampado" class="pane">{estampado_html}</div>'
                          if has_printing else '')

        # Rollo transferido: ribbon verde + origen visible.
        ribbon_html = ''
        origin_html = ''
        if roll.transfer_state == 'transferido':
            ribbon_html = '<div class="ribbon-transfer">Transferido</div>'
            if roll.dest_workorder_id:
                origin_html = f"""
                <div class="row">
                    <span class="label">Transferido a:</span>
                    <span class="value">{escape(roll.dest_workorder_id.display_name or '')}</span>
                </div>"""
        elif roll.transfer_state == 'recibido':
            ribbon_html = '<div class="ribbon-transfer ribbon-received">Recibido</div>'
            src_wo = roll.transfer_origin_roll_id.workorder_id
            if src_wo:
                origin_html = f"""
                <div class="row">
                    <span class="label">Recibido de:</span>
                    <span class="value">{escape(src_wo.display_name or '')}</span>
                </div>"""

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
                .card {{ background: #fff; border-radius: 8px; padding: 20px; max-width: 760px; margin: auto; box-shadow: 0 2px 8px rgba(0,0,0,.1); position: relative; overflow: hidden; }}
                /* Ribbon verde en la esquina superior derecha: rollo transferido */
                .ribbon-transfer {{
                    position: absolute; top: 16px; right: -40px; transform: rotate(45deg);
                    background: #28a745; color: #fff; font-weight: bold; font-size: 0.72rem;
                    letter-spacing: .5px; padding: 5px 48px; box-shadow: 0 1px 3px rgba(0,0,0,.3);
                }}
                .ribbon-received {{ background: #17a2b8; }}
                .title {{ text-align: center; margin-bottom: 20px; color: #333; }}
                .row {{ display: flex; justify-content: space-between; margin-bottom: 12px; }}
                .label {{ font-weight: 600; color: #555; }}
                .value {{ color: #222; }}
                .value a, .reg a {{ color: #1a73e8; text-decoration: none; }}
                .value a:hover, .reg a:hover {{ text-decoration: underline; }}
                .empty {{ color: #888; font-style: italic; text-align: center; padding: 20px 0; }}
                .fibra-wrap {{ width: 100%; margin-bottom: 12px; }}

                /* --- pestañas --- */
                .tabs {{ display: flex; gap: 4px; border-bottom: 2px solid #e0e0e0; margin-bottom: 18px; }}
                .tab {{ background: none; border: none; padding: 10px 18px; cursor: pointer;
                        font-size: 14px; font-weight: 600; color: #777; border-bottom: 3px solid transparent; }}
                .tab.active {{ color: #1a73e8; border-bottom-color: #1a73e8; }}
                .pane {{ display: none; }}
                .pane.active {{ display: block; }}

                /* --- tablas --- */
                table.fibra, table.reg {{ width: 100%; border-collapse: collapse; margin: auto; }}
                table.fibra td:nth-child(2), table.fibra td:nth-child(3) {{ white-space: nowrap; }}
                table.fibra th, table.fibra td, table.reg th, table.reg td {{
                    text-align: left; border: 1px solid #ccc; padding: 4px 6px; font-size: 13px; }}
                table.fibra thead, table.reg thead {{ background: #f0f0f0; }}
            </style>
        </head>
        <body>
            <div class="card">
                {ribbon_html}
                <div class="header">
                    <img src="{logo_url}" alt="Logo" style="max-height: 60px;">
                </div>
                <h1 class="title">Información del rollo</h1>

                <div class="tabs">
                    <button class="tab active" onclick="showTab('tejeduria', this)">Tejeduría</button>
                    <button class="tab" onclick="showTab('tintoreria', this)">Tintorería</button>
                    <button class="tab" onclick="showTab('acabado', this)">Acabado</button>
                    {estampado_tab}
                    <button class="tab" onclick="showTab('calidad', this)">Calidad</button>
                </div>

                <div id="tejeduria" class="pane active">
                    <div class="row">
                        <span class="label">Fecha y Hora:</span>
                        <span class="value">{escape(fmt_dt(roll.create_date))}</span>
                    </div>
                    <div class="row">
                        <span class="label">Número:</span>
                        <span class="value">{escape(roll.name or '')}</span>
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
                        <span class="value">{escape(roll.workorder_id.name or '')}</span>
                    </div>
                    {origin_html}
                    <div class="row">
                        <span class="label">Cliente:</span>
                        <span class="value">{escape(roll.workorder_id.production_id.sale_order_line_id.order_id.partner_id.name or roll.workorder_id.company_id.partner_id.name or '')}</span>
                    </div>
                    <div class="row">
                        <span class="label">Orden de Producción:</span>
                        <span class="value">{of_html}</span>
                    </div>
                    <div class="fibra-wrap">{fibers_html}</div>
                    <div class="row">
                        <span class="label">Maquina:</span>
                        <span class="value">{escape(roll.equipment_id.name or '')}</span>
                    </div>
                    <div class="row">
                        <span class="label">Tejedor:</span>
                        <span class="value">{escape(roll.employee_id.name or '')}</span>
                    </div>
                    {color_html}
                    <div class="row">
                        <span class="label">Inicio:</span>
                        <span class="value">{escape(str(roll.roll_start or ''))}</span>
                    </div>
                    <div class="row">
                        <span class="label">Fin:</span>
                        <span class="value">{escape(str(roll.roll_end or ''))}</span>
                    </div>
                    {option_html}
                </div>

                <div id="tintoreria" class="pane">{tintoreria_html}</div>
                <div id="acabado" class="pane">{acabado_html}</div>
                {estampado_pane}
                <div id="calidad" class="pane">{calidad_html}</div>
            </div>
            <script>
                function showTab(id, btn) {{
                    document.querySelectorAll('.pane').forEach(function(p){{ p.classList.remove('active'); }});
                    document.querySelectorAll('.tab').forEach(function(t){{ t.classList.remove('active'); }});
                    document.getElementById(id).classList.add('active');
                    btn.classList.add('active');
                }}
            </script>
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
