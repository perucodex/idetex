from odoo import models, fields, api
import socket
import ipaddress
from odoo.exceptions import UserError

class BatchAddWizard(models.TransientModel):
    _name = 'batch.add.wizard'
    _description = 'Agregar registros en lote'

    batch_id = fields.Many2one('mrp.workorder.batch', string='Batch')
    product_id = fields.Many2one('product.template', string='Product')
    all_products = fields.Many2many('product.template', string='Product', compute='_compute_count_products')
    count_products = fields.Integer('Count Products', compute='_compute_count_products')
    quantity = fields.Integer('Quantity')
    gross_weight = fields.Float('Gross Weight')
    net_length = fields.Float('Net Length')

    @api.model
    def default_get(self, fields):
        res = super().default_get(fields)
        res['batch_id'] = self.env.context.get('active_ids')[0]
        return res

    @api.depends('batch_id')
    def _compute_count_products(self):
        for rec in self:
            if rec.batch_id:
                rec.all_products = rec.batch_id.wo_roll_ids.product_id
                rec.count_products = len(rec.batch_id.wo_roll_ids.product_id)
                rec.product_id = rec.batch_id.wo_roll_ids.product_id if rec.count_products <= 1 else False
            else:
                rec.all_products = False
                rec.count_products = 0
                rec.product_id = False
    
    def action_add(self):
        """Crear los registros reales y MANTENER el wizard abierto."""
        for line in self:
            lot_id = self.env['stock.lot'].create({'name': line.batch_id.name + '-' + str(len(line.batch_id.wo_roll_ids[0].workorder_id.production_id.roll_ids) + 1).zfill(3), 'product_id': line.product_id.id})
            roll = self.env['mrp.production.roll'].create({
                'production_id': line.batch_id.wo_roll_ids[0].workorder_id.production_id.id,
                'batch_id': line.batch_id.id,
                'lot_id': lot_id.id,
                'quantity': line.quantity,
                'gross_weight': line.gross_weight,
                'net_weight': line.gross_weight,
                'net_length': line.net_length,
            })
            self._print_zpl_to_network(self.create_zpl(roll))
        # NO cerramos el wizard
        return {'type': 'ir.actions.act_window_close'}  # lo quitaremos en la vista

    def action_add_and_continue(self):
        """Igual que add pero sin cerrar."""
        self.action_add()
        # Devolvemos la misma vista del wizard
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'batch.add.wizard',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
            'context': self.env.context,
        }
    
    def create_zpl(self, roll):
        zpl_code = f"""^XA
                    ^PW600
                    ^LL600
                    ^CI28

                    ^FO10,30
                    ^A0N,40,40
                    ^FD{roll.product_id.name}^FS

                    ^FO10,100
                    ^BQN,2,10
                    ^FDPPPPP{roll.product_id.barcode} {roll.lot_id.name.replace('-','')} Q{str(int(roll.gross_weight * 100)).zfill(4)}E^FS

                    ^FO300,110
                    ^A0N,22,22
                    ^FDCódigo: {roll.product_id.default_code}^FS

                    ^FO300,135
                    ^A0N,22,22
                    ^FDRollo: {roll.name}^FS

                    ^FO300,160
                    ^A0N,22,22
                    ^FDLote: {roll.lot_id.name}^FS

                    ^FO300,185
                    ^A0N,22,22
                    ^FDPeso: {roll.gross_weight} kg^FS

                    ^FO300,210
                    ^A0N,22,22
                    ^FDMetros: {roll.net_length}^FS

                    ^FO300,235
                    ^A0N,22,22
                    ^FDUsuario: {roll.create_uid.name}^FS

                    ^XZ"""
        return zpl_code
        
    def _print_zpl_to_network(self, zpl_code, printer_ip='172.16.64.95', port=9100):
        """Envía ZPL a impresora por socket TCP/IP."""
        try:
            # 1. Validar IP
            ip = str(ipaddress.ip_address(printer_ip.strip()))
            # 2. Enviar
            with socket.create_connection((ip, port), timeout=5) as sock:
                sock.sendall(zpl_code.encode('utf-8'))
        except (socket.error, UnicodeError, ValueError) as e:
            raise UserError("No se pudo imprimir (verificá IP): %s" % e)
        