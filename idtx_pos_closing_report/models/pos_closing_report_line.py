# -*- coding: utf-8 -*-
from odoo import models, fields, api

class PosClosingReportLine(models.Model):
    """
    Modelo técnico utilizado para persistir los datos del reporte de cierre de caja.
    Su función principal es permitir la visualización de la 'Tabla Detallada' (Vista Lista)
    dentro de Odoo, replicando la experiencia de las vistas de existencias sugeridas.
    
    Los registros se generan temporalmente cada vez que se solicita el reporte interactivo.
    """
    _name = 'pos.closing.report.line'
    _description = 'Línea de Reporte de Cierre de Caja'
    _order = 'date asc, id asc'

    session_id = fields.Many2one('pos.session', string='Sesión', index=True, ondelete='cascade')
    currency_id = fields.Many2one('res.currency', related='session_id.currency_id', store=True)
    date = fields.Datetime(string='Fecha')
    kilos = fields.Float(string='Cantidad', digits='Product Unit of Measure')
    product_code = fields.Char(string='Código Producto')
    product_name = fields.Char(string='Producto')
    color_code = fields.Char(string='Código Color')
    color_name = fields.Char(string='Color')
    batch = fields.Char(string='Partida')
    ref = fields.Char(string='Referencia')
    lot_name = fields.Char(string='Lote')
    price_unit = fields.Monetary(string='Precio', currency_field='currency_id')
    doc_number = fields.Char(string='Documento')
    partner_name = fields.Char(string='Cliente')
    partner_vat = fields.Char(string='RUC')
    
    def _get_session_selection(self):
        """Genera dinámicamente las opciones para el searchpanel."""
        sessions = self.env['pos.session'].search([], order='start_at desc, id desc', limit=100) # Limitamos por rendimiento
        res = []
        for s in sessions:
            sn = s.name.split('/')[-1] if '/' in s.name else s.name
            sd = fields.Date.to_string(s.start_at.date()) if s.start_at else ''
            label = f"{sn} - {sd}"
            res.append((label, label))
        return res

    session_display_name = fields.Selection(selection='_get_session_selection', string='Numero de sesion')

    @api.model
    def _search_panel_selection_range(self, field_name, **kwargs):
        """
        Override central para forzar el orden descendente de las sesiones.
        Header (Odoo 19 Compatibility)
        """
        res = super(PosClosingReportLine, self)._search_panel_selection_range(field_name, **kwargs)
        if field_name == 'session_display_name':
            # Forzamos el orden descendente basado en el ID que es el string '0000X - ...'
            res.sort(key=lambda v: v['id'], reverse=True)
        return res

    @api.model
    def search_panel_select_range(self, field_name, **kwargs):
        """
        Override para capturar la llamada de categorías (select='one').
        Header (Odoo 19 Compatibility)
        """
        res = super(PosClosingReportLine, self).search_panel_select_range(field_name, **kwargs)
        if field_name == 'session_display_name' and 'values' in res:
            res['values'].sort(key=lambda v: v['id'], reverse=True)
        return res

    @api.model
    def search_panel_select_multi_range(self, field_name, **kwargs):
        """
        Override para capturar la llamada de filtros (select='multi').
        Header (Odoo 19 Compatibility)
        """
        res = super(PosClosingReportLine, self).search_panel_select_multi_range(field_name, **kwargs)
        if field_name == 'session_display_name' and 'values' in res:
            res['values'].sort(key=lambda v: v['id'], reverse=True)
        return res
    
    amount_cash = fields.Monetary(string='Efectivo', currency_field='currency_id')
    amount_account = fields.Monetary(string='Deposito', currency_field='currency_id')
    amount_card = fields.Monetary(string='Tarjeta', currency_field='currency_id')
    
    entry_type = fields.Selection([
        ('initial', 'Saldo Inicial'),
        ('sale', 'Venta'),
        ('cash_move', 'Movimiento de Efectivo')
    ], string='Tipo')

    @api.model
    def action_open_closing_report(self):
        """
        Punto de entrada directo desde el menú.
        Busca la sesión más reciente (abierta o cerrada hoy),
        sincroniza sus datos y abre la vista de lista.
        """
        # Buscar la sesión más reciente
        session = self.env['pos.session'].search([], order='id desc', limit=1)
        
        if not session:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Sin Sesiones',
                    'message': 'No se encontró ninguna sesión de TPV registrada.',
                    'type': 'warning',
                    'sticky': False,
                }
            }

        # Sincronizar datos para esta sesión
        # Usamos el wizard como puente para la lógica de agregación
        wizard = self.env['pos.closing.report.wizard'].create({'session_id': session.id})
        wizard.action_generate_report()
        wizard.unlink() # Limpiar el wizard temporal

        # Título formateado: "[0000X] [Fecha]"
        session_number = session.name.split('/')[-1] if '/' in session.name else session.name
        session_date = fields.Date.to_string(session.start_at.date()) if session.start_at else ''
        display_title = f"{session_number} {session_date}"

        return {
            'name': f'Reporte de Cierre: {display_title}',
            'type': 'ir.actions.act_window',
            'res_model': 'pos.closing.report.line',
            'view_mode': 'list',
            'search_view_id': self.env.ref('idtx_pos_closing_report.idtx_view_pos_closing_report_line_search').id,
            'context': {'search_default_session_id': session.id},
            'target': 'current',
        }
