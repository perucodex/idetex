# -*- coding: utf-8 -*-
from odoo import models, fields, api, tools

class IdtxPosStockReport(models.Model):
    _name = "idtx.pos.stock.report"
    _inherit = "pos.load.mixin"
    _description = "Reporte de Existencias PdV"
    _auto = False
    _table = "idtx_pos_stock_report"

    # Campos de Navegación (IDs)
    product_id = fields.Many2one('product.product', string='Producto', readonly=True)
    lot_id = fields.Many2one('stock.lot', string='Lote', readonly=True)
    roll_id = fields.Many2one('mrp.production.roll', string='Referencia', readonly=True)
    
    # Campos de Búsqueda/Texto (JSONB Logic)
    product_name = fields.Char('Descripción Producto', readonly=True)
    product_code = fields.Char('Código Producto', readonly=True)
    product_label = fields.Char('Producto Detallado', readonly=True)
    lot_name = fields.Char('Número de Lote', readonly=True)
    partida = fields.Char('Partida', readonly=True)
    partida_label = fields.Char('Partida Detallada', readonly=True)
    roll_name = fields.Char('Número de Referencia', readonly=True)

    # Campos de Color (Manejados vía SQL Join en init)
    color_code = fields.Char('Código Color', readonly=True)
    color_name = fields.Char('Nombre Color', readonly=True)
    
    quantity = fields.Float('Stock (Kg)', readonly=True)
    location_id = fields.Many2one('stock.location', string='Ubicación', readonly=True)
    write_date = fields.Datetime('Última Actualización', readonly=True)

    @api.model
    def _load_pos_data_fields(self, config):
        return [
            'id', 'product_id', 'product_name', 'product_code', 'product_label',
            'lot_id', 'lot_name', 'partida', 'partida_label', 'roll_id', 'roll_name',
            'color_code', 'color_name', 'quantity', 'location_id', 'write_date'
        ]

    @api.model
    def _load_pos_data_domain(self, data, config):
        return []

    @api.model
    def _server_date_to_domain(self, domain):
        # Evitar que Odoo inyecte un filtro de 'write_date' para carga incremental si no queremos,
        # pero ahora que lo tenemos en la vista, podemos dejarlo o controlarlo.
        return domain

    def reprint(self):
        """ Lógica de reimpresión movida aquí para evitar modificar módulos externos """
        import socket
        import ipaddress
        from odoo.exceptions import UserError
        
        printer_ip = self.env.company.zpl_printer_ip
        if not printer_ip:
            raise UserError("La IP de la impresora no está configurada en la compañía.")
            
        quant_ids = self.ids
        quants = self.env['stock.quant'].browse(quant_ids)
        for quant in quants:
            if quant.lot_id:
                # Buscar rollo asociado al lote
                roll = self.env['mrp.production.roll'].search([('lot_id', '=', quant.lot_id.id)], limit=1)
                if roll:
                    zpl_code = roll.create_zpl(quant.quantity)
                    try:
                        ip = str(ipaddress.ip_address(printer_ip.strip()))
                        with socket.create_connection((ip, 9100), timeout=5) as sock:
                            sock.sendall(zpl_code.encode('utf-8'))
                    except (socket.error, UnicodeError, ValueError) as e:
                        raise UserError("No se pudo imprimir (verificá IP): %s" % e)

    def action_reubicar(self):
        """ Llama al asistente estándar de Odoo para reubicar quants """
        quant_ids = self.ids
        quants = self.env['stock.quant'].browse(quant_ids)
        res = quants.action_stock_quant_relocate()
        res['context'].update({'from_pos_stock_report': True})
        return res

    def action_screen_barcode(self):
        wizard = self.env['pos.stock.barcode.wizard'].create({
            'report_ids': [(6, 0, self.ids)]
        })
        return {
            'name': 'Screen Bar Code',
            'type': 'ir.actions.act_window',
            'res_model': 'pos.stock.barcode.wizard',
            'res_id': wizard.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW %s AS (
                SELECT
                    q.id AS id,
                    q.product_id AS product_id,
                    pt.default_code AS product_code,
                    '[' || pt.default_code || '] ' || COALESCE(pt.name->>'es_PE', pt.name->>'en_US', pt.name->>'und') AS product_label,
                    COALESCE(pt.name->>'es_PE', pt.name->>'en_US', pt.name->>'und') AS product_name,
                    q.lot_id AS lot_id,
                    l.name AS lot_name,
                    CASE 
                        WHEN LENGTH(l.name) > 4 THEN LEFT(l.name, LENGTH(l.name) - 4)
                        ELSE l.name 
                    END AS partida,
                    '[' || pt.default_code || '] ' || COALESCE(pt.name->>'es_PE', pt.name->>'en_US', pt.name->>'und') || ' | ' || COALESCE(ldl.color_name, 'S/C') || ' | P:' || 
                    CASE 
                        WHEN LENGTH(l.name) > 4 THEN LEFT(l.name, LENGTH(l.name) - 4)
                        ELSE l.name 
                    END AS partida_label,
                    ldl.color_code AS color_code,
                    ldl.color_name AS color_name,
                    r.id AS roll_id,
                    r.name AS roll_name,
                    q.quantity AS quantity,
                    q.location_id AS location_id,
                    q.write_date AS write_date
                FROM
                    stock_quant q
                JOIN
                    product_product pp ON pp.id = q.product_id
                JOIN
                    product_template pt ON pt.id = pp.product_tmpl_id
                JOIN
                    stock_location sl ON sl.id = q.location_id
                LEFT JOIN
                    stock_lot l ON l.id = q.lot_id
                LEFT JOIN
                    color_recipe cr ON cr.id = l.color_recipe_id
                LEFT JOIN
                    lab_dev_line ldl ON ldl.id = cr.lab_dev_line_id
                LEFT JOIN
                    mrp_production_roll r ON r.id = l.roll_id
                WHERE
                    q.quantity > 0
                    AND pt.available_in_pos = True
                    AND sl.usage = 'internal'
            )
        """ % self._table)

class StockQuantRelocate(models.TransientModel):
    _inherit = 'stock.quant.relocate'

    def action_relocate_quants(self):
        res = super(StockQuantRelocate, self).action_relocate_quants()
        if self.env.context.get('from_pos_stock_report'):
            return self.env.ref('idtx_pos_report_stock.action_idtx_pos_stock_report').read()[0]
        return res

class PosStockBarcodeWizard(models.TransientModel):
    _name = 'pos.stock.barcode.wizard'
    _description = 'Screen Barcode Wizard'

    report_ids = fields.Many2many('idtx.pos.stock.report', string='Reports')
    label_html = fields.Html('Etiquetas', compute='_compute_label_html')

    @api.depends('report_ids')
    def _compute_label_html(self):
        import qrcode
        import base64
        from io import BytesIO
        
        for wizard in self:
            html = "<div style='display: flex; flex-direction: column; gap: 20px; align-items: center;'>"
            for rep in wizard.report_ids:
                weight = rep.quantity or 0.0
                barcode = rep.product_id.barcode or ''
                barcode_data = f"01{barcode}3102{str(int(round(weight * 100))).zfill(6)}10{rep.lot_name or ''}"
                
                # Generar QR localmente
                qr = qrcode.QRCode(version=1, box_size=4, border=0)
                qr.add_data(barcode_data)
                qr.make(fit=True)
                img = qr.make_image(fill_color="black", back_color="white")
                buffer = BytesIO()
                img.save(buffer, format="PNG")
                qr_base64 = base64.b64encode(buffer.getvalue()).decode("utf-8")
                qr_url = f"data:image/png;base64,{qr_base64}"
                
                html += f'''
                <div style="width: 480px; border: 1px solid #000; padding: 15px; border-radius: 4px; font-family: 'Arial', sans-serif; background: #fff; margin-bottom: 20px; color: #000;">
                    <div style="font-size: 22px; font-weight: bold; margin-bottom: 10px; text-transform: uppercase;">
                        {rep.product_name or ''}
                    </div>
                    <div style="display: flex; justify-content: space-between;">
                        <!-- Columna Izquierda: QR y Número de Rollo -->
                        <div style="display: flex; flex-direction: column; align-items: center; justify-content: flex-start; width: 40%;">
                            <img src="{qr_url}" style="width: 160px; height: 160px; margin-bottom: 5px;"/>
                            <div style="font-size: 14px; font-weight: bold;">
                                {rep.roll_name or ''}
                            </div>
                        </div>

                        <!-- Columna Derecha: Detalles -->
                        <div style="display: flex; flex-direction: column; width: 55%; font-size: 14px; line-height: 1.2;">
                            <div style="margin-bottom: 2px;"><strong>Código:</strong> {rep.product_code or ''}</div>
                            <div style="margin-bottom: 2px;"><strong>Color:</strong> [{rep.color_code or ''}]</div>
                            <div style="font-size: 18px; font-weight: bold; margin-bottom: 4px;">{rep.color_name or ''}</div>
                            <div style="font-size: 16px; margin-bottom: 12px;"><strong>Lote:</strong> {rep.lot_name or ''}</div>
                            
                            <div style="text-align: center;">
                                <div style="font-size: 16px;">Peso</div>
                                <div style="font-size: 38px; font-weight: bold; margin-top: -2px;">{weight:.2f}</div>
                            </div>
                        </div>
                    </div>
                </div>
                '''
            html += "</div>"
            wizard.label_html = html

    def action_print(self):
        self.ensure_one()
        self.report_ids.reprint()
        return {'type': 'ir.actions.act_window_close'}

