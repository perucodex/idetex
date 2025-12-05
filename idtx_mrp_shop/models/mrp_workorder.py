from odoo import _, models
import requests

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
                roll._print_zpl_to_network(roll.create_zpl(), self.env.company.zpl_printer_ip)
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