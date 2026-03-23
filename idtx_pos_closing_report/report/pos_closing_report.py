# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from datetime import datetime

class PosClosingControlReport(models.AbstractModel):
    _name = 'report.idtx_pos_closing_report.report_closing_control'
    _description = 'Lógica del Reporte de Cierre de Caja'

    @api.model
    def _get_report_values(self, docids, data=None):
        """
        Lógica central del reporte. 
        Este método se encarga de:
        1. Identificar la sesión de TPV seleccionada.
        2. Recopilar todas las órdenes de la sesión y desglosar sus líneas de productos.
        3. Clasificar los pagos de cada orden en tres categorías: Efectivo, Cuenta Cliente o Tarjeta.
        4. Buscar detalles de trazabilidad (Partida, Referencia) a través de los lotes vendidos.
        5. Obtener los movimientos manuales de caja (Entradas/Salidas) de la sesión.
        6. Consolidar todo en una lista cronológica 'entries' para el PDF o la Vista Interactiva.
        """
        wizard = self.env['pos.closing.report.wizard'].browse(docids)
        wizard.ensure_one()
        session = wizard.session_id

        # Saldo inicial de la sesión de TPV
        opening_balance = session.cash_register_balance_start
        
        # Lista que contendrá la mezcla de ventas y movimientos manuales
        entries = []
        
        # 1. Obtener órdenes y sus líneas cronológicamente
        orders = self.env['pos.order'].search([('session_id', '=', session.id)], order='date_order asc')
        
        total_kilos = 0
        total_efectivo = 0
        total_cuenta = 0
        total_tarjeta = 0
        
        # Variable para llevar el seguimiento del saldo de caja proyectado
        current_cash_balance = opening_balance

        # 0. Agregar Saldo Inicial como primera entrada
        # Le restamos un segundo para asegurar que sea el primero tras el sort
        start_date = session.start_at or session.create_date
        initial_date = fields.Datetime.to_datetime(start_date)
        
        entries.append({
            'date': initial_date,
            'kilos': 0,
            'name_color': _('Saldo Inicial de Apertura'),
            'price': 0,
            'number': '',
            'efectivo': opening_balance,
            'cuenta': 0,
            'tarjeta': 0,
            'partner_name': '',
            'partner_vat': '',
            'type': 'initial'
        })

        for order in orders:
            # Determinamos el número de documento (Factura/Boleta si existe, sino Referencia POS)
            doc_number = order.account_move.name or order.pos_reference
            
            # Clasificamos los pagos de la orden para las columnas del reporte
            order_cash = 0
            order_cuenta = 0
            order_tarjeta = 0
            
            for payment in order.payment_ids:
                pm = payment.payment_method_id
                amount = payment.amount
                
                # Clasificación basada en tipo de método (Efectivo) o palabras clave (Cuentas/Crédito)
                if pm.is_cash_count:
                    order_cash += amount
                elif 'CUENTA' in pm.name.upper() or 'CLIENTE' in pm.name.upper() or 'CREDITO' in pm.name.upper():
                    order_cuenta += amount
                else:
                    order_tarjeta += amount

            # Procesamos cada línea de producto dentro de la orden
            for line in order.lines:
                kilos = line.qty
                price = line.price_unit
                
                # Buscamos el lote para extraer datos de Partida y Referencia (MRP)
                lot_name = line.pack_lot_ids[0].lot_name if line.pack_lot_ids else False
                lot = self.env['stock.lot'].search([('name', '=', lot_name), ('product_id', '=', line.product_id.id)], limit=1) if lot_name else False
                
                # Nombre con Color (concatenado para fallback)
                name_color = line.product_id.name
                if line.lot_color_name:
                    name_color += f" {line.lot_color_name}"
                
                # Los montos de pago se muestran solo en la primera línea de la orden para evitar duplicar el total al sumar la columna
                is_first_line = (line == order.lines[0])
                
                # Truncamos strings solo para el reporte (visualización)
                p_name = (line.product_id.name or '')[:25]
                c_name = (lot.color_name or '')[:20] if lot else ''
                d_num = (doc_number or '')[:15]

                entries.append({
                    'date': order.date_order,
                    'kilos': kilos,
                    'product_code': line.product_id.default_code or '',
                    'product_name': p_name,
                    'color_code': lot.color_code or '' if lot else '',
                    'color_name': c_name,
                    'batch': lot.roll_id.batch_id.name if lot and lot.roll_id and lot.roll_id.batch_id else '',
                    'ref': lot.roll_id.name if lot and lot.roll_id else '',
                    'lot_name': lot.name if lot else '',
                    'name_color': name_color, 
                    'price': price,
                    'number': d_num,
                    'partner_name': order.partner_id.name or '',
                    'partner_vat': order.partner_id.vat or '',
                    'efectivo': order_cash if is_first_line else 0,
                    'cuenta': order_cuenta if is_first_line else 0,
                    'tarjeta': order_tarjeta if is_first_line else 0,
                    'type': 'sale'
                })
                
                total_kilos += kilos
            
            # Acumulamos totales generales del reporte
            total_efectivo += order_cash
            total_cuenta += order_cuenta
            total_tarjeta += order_tarjeta
            current_cash_balance += order_cash

        # 2. Obtener movimientos manuales de efectivo (Ingresos/Salidas de Caja)
        # En v19, session.statement_line_ids contiene estos registros.
        cash_moves = session.statement_line_ids
        
        for move in cash_moves:
            amount = move.amount
            entries.append({
                'date': fields.Datetime.to_datetime(move.date),
                'kilos': 0,
                'name_color': f"MOV: {move.payment_ref or ''}",
                'price': 0,
                'number': move.ref or '',
                'efectivo': amount,
                'cuenta': 0,
                'tarjeta': 0,
                'partner_name': move.partner_id.name or '',
                'partner_vat': move.partner_id.vat or '',
                'type': 'cash_move'
            })
            total_efectivo += amount
            current_cash_balance += amount

        # Ordenamos la mezcla final de ventas y movimientos por fecha/hora
        # Forzamos que 'initial' siempre sea el primero agregando un criterio secundario
        entries.sort(key=lambda x: (x['date'], x['type'] != 'initial'))
        
        # Para el PDF: Queremos que total_efectivo incluya el saldo inicial si queremos que cuadre
        total_efectivo += opening_balance

        return {
            'doc_ids': docids,
            'doc_model': 'pos.closing.report.wizard',
            'docs': wizard,
            'session': session,
            'opening_balance': opening_balance,
            'entries': entries,
            'total_kilos': total_kilos,
            'total_efectivo': total_efectivo,
            'total_cuenta': total_cuenta,
            'total_tarjeta': total_tarjeta,
            'final_cash_balance': current_cash_balance,
        }
