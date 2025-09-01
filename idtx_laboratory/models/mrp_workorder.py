from odoo import _, models, fields, api
import requests

class MrpWorkorder(models.Model):
    _inherit = 'mrp.workorder'

    mrwo_id = fields.Many2one('mrp.routing.workcenter.operation', string='Operation LAB')
    roll_ids = fields.One2many('mrp.workorder.roll', 'workorder_id', string='Weaving Rolls')
    batch_ids = fields.One2many('mrp.workorder.batch', 'workorder_id', string='Batchs')
    # weaving_wo = fields.Boolean(related='mrwo_id.is_weaving')
    operation_type = fields.Selection(related='mrwo_id.operation_type')
    weave_type = fields.Selection(related='product_id.product_tmpl_id.technical_sheet_id.weave_type', store=True)
    roll_weight = fields.Float('Roll Weight', compute='_compute_progress')
    quantity = fields.Float('Quantity LAB', compute='_compute_progress')
    progress = fields.Float('Progress')
    equipment_ids = fields.Many2many('maintenance.equipment', string='Equipments')
    equipment_id = fields.Many2one('maintenance.equipment', string='Equipment')

    @api.depends('roll_ids','batch_ids')
    def _compute_progress(self):
        for rec in self:
            if rec.operation_type == 'weaving':
                if rec.weave_type == 'rect':
                    rec.quantity = sum(rec.roll_ids.mapped('quantity'))
                    rec.progress = (rec.quantity / rec.qty_remaining) * 100 if rec.qty_remaining else 100
                    rec.roll_weight = 0
                else:
                    rec.roll_weight = sum(rec.roll_ids.mapped('gross_weight'))
                    rec.progress = (rec.roll_weight / rec.qty_remaining) * 100 if rec.qty_remaining else 100
                    rec.quantity = 0
            # elif rec.operation_type == 'dyeing':
            #     if rec.batch_ids:
            #         if sum(rec.batch_ids.wo_roll_ids.mapped('gross_weight')) > 0:
            #             rec.roll_weight = sum(rec.batch_ids.wo_roll_ids.mapped('gross_weight'))
            #             rec.progress = (rec.roll_weight / rec.qty_remaining) * 100 if rec.qty_remaining else 100
            #             rec.quantity = 0
            #         else:
            #             rec.quantity = sum(rec.batch_ids.wo_roll_ids.mapped('quantity'))
            #             rec.progress = (rec.quantity / rec.qty_remaining) * 100 if rec.qty_remaining else 100
            #             rec.roll_weight = 0
            else:
                rec.quantity = 0
                rec.roll_weight = 0
                rec.progress = 0

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
                self.roll_ids.create({
                    'sequence': len(self.roll_ids),
                    'workorder_id': self.id,
                    'gross_weight': peso,
                    'net_weight': peso,
                    'employee_id': int(employee_id),
                    'equipment_id': int(equipment_id),
                })
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
        
    def get_available_sizes(self):
        '''Devuelve las tallas (size_chart_ids) del producto relacionado'''
        self.ensure_one()
        sizes = self.product_id.product_tmpl_id.technical_sheet_id.size_chart_ids
        return [{'id': s.id, 'size': s.size} for s in sizes]
    
    def action_create_size_record(self, size_id, quantity, employee_id, equipment_id):
        self.roll_ids.create({
            'sequence': len(self.roll_ids),
            'workorder_id': self.id,
            'employee_id': self.employee_id.id,
            'size_id': size_id,
            'quantity': quantity,
            'employee_id': employee_id,
            'equipment_id': equipment_id,
        })