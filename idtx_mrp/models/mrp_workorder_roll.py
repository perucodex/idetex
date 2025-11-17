from odoo import _, models, fields, api
from odoo.exceptions import UserError
import socket
import ipaddress

class MrpWorkorderRoll(models.Model):
    _name = "mrp.workorder.roll"
    _description = 'Mrp Workorder Roll'

    workorder_id = fields.Many2one('mrp.workorder', string='Workorder')
    sequence = fields.Integer('Sequence')
    name = fields.Char('Number')
    product_id = fields.Many2one(related='workorder_id.product_id.product_tmpl_id')
    uom_id = fields.Many2one(related='workorder_id.product_id.product_tmpl_id.uom_id')
    quantity = fields.Integer('Quantity')
    gross_weight = fields.Float('Gross Weight')
    net_weight = fields.Float('Net Weight')
    in_batch = fields.Boolean('in_batch?', default=False)
    new_weight = fields.Float('Split new weight')
    equipment_id = fields.Many2one('maintenance.equipment', string='Equipment')
    employee_id = fields.Many2one('hr.employee', string='Employee')

    def reprint(self):
        for rec in self:
            rec._print_zpl_to_network(rec.create_zpl())

    #=== CRUD METHODS ===#

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            vals['name'] = self.env['ir.sequence'].with_company(vals.get('company_id')).next_by_code('mrp.workorder.roll')
        return super().create(vals_list)
    
    def unlink(self):
        roll_names = ''
        for rec in self:
            if rec.in_batch:
                roll_names += rec.name + '\n'
        if roll_names:
            raise UserError(_('Can\'t delete a roll that is in a batch process.\nRolls:\n%s') %roll_names)
        return super().unlink()

    def split(self):
        return {
            'name': _('Divide Roll'),
            'view_mode': 'form',
            'res_model': 'split.roll',
            'views': [(self.env.ref('idtx_mrp.split_roll_form').id, 'form')],
            'type': 'ir.actions.act_window',
            'target': 'new',
            'context': dict(self.env.context)
        }

    def create_zpl(self):
        self.ensure_one()
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url') #"https://odoo.gestionidtx.com/rollo"
        url = f"{base_url}/rollo/{self.id}/datos"
        zpl_code = f"""^XA
                    ^PW600
                    ^LL600
                    ^CI28

                    ^FO20,30
                    ^A0N,40,40
                    ^FD{self.product_id.name}^FS

                    ^FO100,100
                    ^BQN,2,8.5
                    ^FDLA,{url}^FS

                    ^FO300,110
                    ^A0N,22,22
                    ^FDCódigo: {self.product_id.default_code}^FS

                    ^FO300,135
                    ^A0N,22,22
                    ^FDRollo: {self.name}^FS

                    ^FO300,160
                    ^A0N,22,22
                    ^FDPeso: {self.gross_weight}^FS

                    ^FO300,185
                    ^A0N,22,22
                    ^FDPeso Neto: {self.net_weight} kg^FS

                    ^FO300,210
                    ^A0N,22,22
                    ^FDMaquina: {self.equipment_id.name}^FS

                    ^FO300,235
                    ^A0N,22,22
                    ^FDUsuario: {self.employee_id.name}^FS

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