# -*- coding: utf-8 -*-
from odoo import models, fields, api, _

class PosClosingReportWizard(models.TransientModel):
    _name = 'pos.closing.report.wizard'
    _description = 'Wizard de Reporte de Cierre de Caja'

    session_id = fields.Many2one(
        'pos.session', 
        string='Sesión de TPV', 
        required=True,
        domain="[('state', 'in', ['opened', 'closing_control', 'closed'])]"
    )

    def action_generate_report(self):
        """
        Proceso para generar la Tabla Detallada Interactiva:
        1. Limpia los datos previos de la sesión para evitar duplicados.
        2. Llama a la lógica centralizada de agregación (_get_report_values).
        3. Convierte los datos procesados en registros de 'pos.closing.report.line'.
        4. Redirige al usuario a la vista de lista de dichos registros.
        """
        self.ensure_one()
        # 1. Limpiar líneas previas de esta sesión
        self.env['pos.closing.report.line'].search([('session_id', '=', self.session_id.id)]).unlink()
        
        # 2. Obtener valores usando la lógica centralizada para evitar discrepancias con el PDF
        report_obj = self.env['report.idtx_pos_closing_report.report_closing_control']
        vals = report_obj._get_report_values([self.id])
        
        # 3. Poblar el modelo de vista interactiva
        session_number = vals['session'].name.split('/')[-1] if '/' in vals['session'].name else vals['session'].name
        session_date = fields.Date.to_string(vals['session'].start_at.date()) if vals['session'].start_at else ''
        display_name = f"{session_number} - {session_date}"

        line_vals = []
        for entry in vals['entries']:
            line_vals.append({
                'session_id': self.session_id.id,
                'session_display_name': display_name,
                'date': entry['date'],
                'kilos': entry['kilos'],
                'product_code': entry.get('product_code', ''),
                'product_name': entry.get('product_name', '') if entry['type'] == 'sale' else entry['name_color'],
                'color_code': entry.get('color_code', ''),
                'color_name': entry.get('color_name', ''),
                'batch': entry.get('batch', ''),
                'ref': entry.get('ref', ''),
                'lot_name': entry.get('lot_name', ''),
                'price_unit': entry['price'],
                'doc_number': entry['number'],
                'partner_name': entry.get('partner_name', ''),
                'partner_vat': entry.get('partner_vat', ''),
                'amount_cash': entry['efectivo'],
                'amount_account': entry['cuenta'],
                'amount_card': entry['tarjeta'],
                'entry_type': entry['type']
            })
        
        if line_vals:
            self.env['pos.closing.report.line'].create(line_vals)
            
        # 4. Retornar acción para abrir la vista de tabla con agrupamiento por sesión
        return {
            'name': 'Reporte Cierre Detallado',
            'type': 'ir.actions.act_window',
            'res_model': 'pos.closing.report.line',
            'view_mode': 'list',
            'domain': [('session_id', '=', self.session_id.id)],
            'target': 'current',
        }

    def action_print_pdf(self):
        """Dispara la generación del reporte PDF estándar."""
        self.ensure_one()
        return self.env.ref('idtx_pos_closing_report.action_report_closing_control').report_action(self)
