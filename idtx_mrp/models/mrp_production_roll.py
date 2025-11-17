from odoo import _, models, fields, api
from odoo.exceptions import UserError
import socket
import ipaddress

class MrpProductionRoll(models.Model):
    _name = "mrp.production.roll"
    _description = 'Mrp Production Roll'

    production_id = fields.Many2one('mrp.production', string='Production')
    sequence = fields.Integer('Sequence')
    batch_id = fields.Many2one('mrp.workorder.batch', string='Batch')
    name = fields.Char('Number')
    product_id = fields.Many2one(related='production_id.product_id.product_tmpl_id')
    uom_id = fields.Many2one(related='production_id.product_id.product_tmpl_id.uom_id')
    lot_id = fields.Many2one('stock.lot', 'Lot')
    quantity = fields.Integer('Quantity', default=1)
    gross_weight = fields.Float('Gross Weight')
    net_weight = fields.Float('Net Weight')
    net_length = fields.Float('Net Length')
    equipment_id = fields.Many2one('maintenance.equipment', string='Equipment')
    employee_id = fields.Many2one('hr.employee', string='Employee')

    def reprint(self):
        for rec in self:
            rec._print_zpl_to_network(rec.create_zpl(rec.quantity))  

    #=== CRUD METHODS ===#

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            vals['name'] = self.env['ir.sequence'].with_company(vals.get('company_id')).next_by_code('mrp.production.roll')
        return super().create(vals_list)
    
    def create_zpl(self, weight=0):
        self.ensure_one()
        weight = self.gross_weight if not weight else weight
        zpl_code = f"""^XA
                    ^PW600
                    ^LL600
                    ^CI28

                    ^FO20,30
                    ^A0N,40,40
                    ^FD{self.product_id.name}^FS

                    ^FO20,100
                    ^BQN,2,10
                    ^FDLA,01{self.product_id.barcode}3102{str(int(weight * 100)).zfill(6)}10{self.lot_id.name}^FS

                    ^FO300,110
                    ^A0N,22,22
                    ^FDCódigo: {self.product_id.default_code}^FS

                    ^FO300,135
                    ^A0N,22,22
                    ^FDColor: [{self.lot_id.color_code}]^FS

                    ^FO300,160
                    ^A0N,28,28
                    ^FD{self.lot_id.color_name}^FS

                    ^FO300,195
                    ^A0N,28,28
                    ^FDLote: {self.lot_id.name}^FS

                    ^FO380,235
                    ^A0N,30,30
                    ^FDPeso^FS

                    ^FO330,285
                    ^A0N,60,60
                    ^FD{weight} kg^FS

                    ^FO80,375
                    ^A0N,22,22
                    ^FD{self.name}^FS

                    ^XZ"""
        return zpl_code

                    # ^FO300,270
                    # ^A0N,22,22
                    # ^FDMetros: {self.net_length}^FS

                    # ^FO300,295
                    # ^A0N,22,22
                    # ^FDUsuario: {self.create_uid.name}^FS
        
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