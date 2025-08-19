from odoo import _, models, fields, api
import requests
# from odoo.http import request
import socket
from odoo.exceptions import UserError

class MrpWorkorder(models.Model):
    _inherit = "mrp.workorder"

    mrwo_id = fields.Many2one('mrp.routing.workcenter.operation', string='Operation')
    roll_ids = fields.One2many('mrp.workorder.roll', 'workorder_id', string='Weaving Rolls')
    weaving_wo = fields.Boolean(related='mrwo_id.is_weaving')
    weave_type = fields.Selection(related='product_id.product_tmpl_id.technical_sheet_id.weave_type')
    roll_weight = fields.Float('Roll Weight', compute='_compute_progress')
    quantity = fields.Float('Quantity', compute='_compute_progress')
    progress = fields.Float('Progress')
    equipment_ids = fields.Many2many('maintenance.equipment', string='Equipment')

    @api.depends('roll_ids')
    def _compute_progress(self):
        for rec in self:
            if rec.weave_type == 'rect':
                rec.quantity = sum(rec.roll_ids.mapped('quantity'))
                rec.progress = (rec.quantity / rec.qty_remaining) * 100 if rec.qty_remaining else 100
                rec.roll_weight = 0
            else:
                rec.roll_weight = sum(rec.roll_ids.mapped('gross_weight'))
                rec.progress = (rec.roll_weight / rec.qty_remaining) * 100 if rec.qty_remaining else 100
                rec.quantity = 0

    # @api.onchange('mrwo_id')
    # def _onchange_mrwo_id(self):
    #     for rec in self:
    #         rec.name = rec.mrwo_id.name
    #         if rec.mrwo_id:
    #             rec.workcenter_id = rec.mrwo_id.workcenter_id
    
    def get_local_ip(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            # No se conecta realmente, solo fuerza a obtener la IP
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
        except Exception:
            ip = "127.0.0.1"
        finally:
            s.close()
        return ip

    def action_read_scale(self):
        """Leer la balanza desde el endpoint Flask"""
        try:
            # Cambia la IP o hostname al de la PC donde corre Flask
            ip = self.get_local_ip()
            url = f'http://{ip}:5001/peso'
            resp = requests.get(url, timeout=3)
            resp.raise_for_status()
            data = resp.json()

            if data.get("ok") and data.get("peso") is not None:
                peso = 27.32#data["peso"]
                self.qty_producing = sum(self.roll_ids.mapped('gross_weight'))
                if peso:
                    self.roll_ids.create({
                        'sequence': len(self.roll_ids),
                        'workorder_id': self.id,
                        'gross_weight': peso,
                        'net_weight': peso,
                        'employee_id': self.employee_id,
                    })
                    return {
                        'type': 'ir.actions.client',
                        'tag': 'display_notification',
                        'params': {
                            'title': 'Peso leído',
                            'message': f'Peso agregado: {peso} kg orden de fabricación {self.production_id.name}',
                            'type': 'success',
                            'sticky': False,
                        }
                    }
                else:
                    return {
                        'type': 'ir.actions.client',
                        'tag': 'display_notification',
                        'params': {
                            'title': 'Peso no leído',
                            'message': f'No hay ningun peso en la balanza orden de fabricación {self.production_id.name}',
                            'type': 'danger',
                            'sticky': False,
                        }
                    }
            else:
                raise UserError("No se obtuvo un peso válido de la balanza")
        except Exception as e:
            raise UserError(f"Error al consultar balanza: {str(e)}")