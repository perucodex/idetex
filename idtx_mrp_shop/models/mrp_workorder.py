from odoo import _, models
import requests
import socket
import ipaddress
from odoo.exceptions import UserError

class MrpWorkorder(models.Model):
    _inherit = 'mrp.workorder'

    def action_read_scale(self, id, employee_id, equipment_id, manual_weight=None):
        '''Leer la balanza desde el endpoint Flask'''
        '''Los parametros vienen de JavaScript'''
        try:
            if round(manual_weight,2):
                peso = float(round(manual_weight,2))
            else:
            # Cambia la IP o hostname al de la PC donde corre Flask
                client_ip = self.env['scale.registry'].browse(id).ip
                url = f'http://{client_ip}:5001/peso'
                resp = requests.get(url, timeout=3)
                resp.raise_for_status()
                data = resp.json()

                if data.get('ok') and data.get('peso') is not None:
                    peso = 27.77#data['peso']
                else:
                    return {'status': 'danger', 'message': _('No communication with the scale')}
            if peso:
                roll = self.roll_ids.create({
                    'sequence': len(self.roll_ids),
                    'workorder_id': self.id,
                    'gross_weight': peso,
                    'net_weight': peso,
                    'employee_id': int(employee_id),
                    'equipment_id': int(equipment_id),
                })
                self._print_zpl_to_network(self.create_zpl(roll))
                self.qty_producing = sum(self.roll_ids.mapped('gross_weight'))
                return {
                    'status': 'success',
                    'peso': peso,
                    'message': _(f'Added weight: {peso} kg production order {self.production_id.name}'),
                }
            else:
                self.qty_producing = sum(self.roll_ids.mapped('gross_weight'))
                return {'status': 'danger', 'message': _('No weight was provided')}
        except Exception as e:
            return {'status': 'danger', 'message': _(f'Error: {str(e)}')}
        
    def action_create_size_record(self, size_id, quantity, employee_id, equipment_id):
        self.roll_ids.create({
            'sequence': len(self.roll_ids),
            'workorder_id': self.id,
            'size_id': size_id,
            'quantity': quantity,
            'employee_id': employee_id,
            'equipment_id': equipment_id,
        })

    def action_create_registry_record(self, batch_id, employee_id, equipment_id):
        prd = self.production_id
        recipe = prd.color_recipe_id
        ldl = recipe.lab_dev_line_id
        batch = self.env['mrp.workorder.batch'].search([('id','=', batch_id)])
        br = self.env['batch.registry'].create({
            'batch_id': batch_id,
            'workorder_id': self.id,
            'employee_id': employee_id,
            'equipment_id': equipment_id,
            'bath_ratio': ldl.bath_ratio,
            'color_name': ldl.color_name,
            'color_code': ldl.color_code,
            'partner_id': ldl.lab_dev_id.partner_id.id,
        })
        br._onchange_workorder_id()
        return {
            'status': 'success',
            'batchId': br.id,
            'message': _(f'Registry created for batch {batch.name}'),
        }
    
    def create_zpl(self, roll):
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url') #"https://odoo.gestionidtx.com/rollo"
        url = f"{base_url}/rollo/{roll.id}/datos"
        zpl_code = f"""^XA
                    ^PW600
                    ^LL600
                    ^CI28

                    ^FO10,30
                    ^A0N,40,40
                    ^FD{roll.product_id.name}^FS

                    ^FO10,100
                    ^BQN,2,10
                    ^FDLA,{url}^FS

                    ^FO300,110
                    ^A0N,22,22
                    ^FDCódigo: {roll.product_id.default_code}^FS

                    ^FO300,135
                    ^A0N,22,22
                    ^FDRollo: {roll.name}^FS

                    ^FO300,160
                    ^A0N,22,22
                    ^FDPeso: {roll.gross_weight}^FS

                    ^FO300,185
                    ^A0N,22,22
                    ^FDPeso Neto: {roll.net_weight} kg^FS

                    ^FO300,210
                    ^A0N,22,22
                    ^FDMaquina: {roll.equipment_id.name}^FS

                    ^FO300,235
                    ^A0N,22,22
                    ^FDUsuario: {roll.employee_id.name}^FS

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