from odoo import models, fields, api, _
from odoo.exceptions import UserError

class SplitRoll(models.TransientModel):
    _name = 'split.roll'
    _description = 'Split Roll'

    old_weight = fields.Float('Old Weight')
    new_weight = fields.Float('New Weight')
    old_quantity = fields.Integer('Old Quantity')
    new_quantity = fields.Integer('New Quantity')

    @api.model
    def default_get(self, fields):
        res = super(SplitRoll, self).default_get(fields)
        roll = self.env['mrp.workorder.roll'].browse(self.env.context.get('active_id'))
        if roll.weave_type == 'rect':
            res['old_quantity'] = roll.quantity
            res['new_quantity'] = roll.quantity / 2
        else:
            res['old_weight'] = roll.gross_weight
            res['new_weight'] = roll.gross_weight / 2
        return res

    def split_roll(self):
        roll = self.env['mrp.workorder.roll'].browse(self.env.context.get('active_id'))
        if roll.weave_type == 'rect':
            if self.old_quantity <= self.new_quantity:
                raise UserError(_('New quantity can\'t be greather than old quantity.'))
            prefix = roll.name.split('-')[0]
            existing_rolls = self.env['mrp.workorder.roll'].search([('name','like', f'{prefix}%')])
            used_numbers = []
            for r in existing_rolls:
                parts_name = r.name.split('-')
                if len(parts_name) > 1 and parts_name[1].isdigit():
                    used_numbers.append(int(parts_name[1]))
            next_number = max(used_numbers) + 1 if used_numbers else 1
            if not used_numbers:
                roll.name = f'{prefix}-{str(next_number).zfill(3)}'
                next_number += 1
            new_quantity = round(roll.gross_quantity - self.new_quantity, 2)
            roll.copy({
                'name': f'{prefix}-{str(next_number).zfill(3)}',
                'quantity': self.new_quantity,
            })
            roll.quantity = new_quantity
        else:
            if self.old_weight <= self.new_weight:
                raise UserError(_('New weight can\'t be greather than gross weight.'))
            prefix = roll.name.split('-')[0]
            existing_rolls = self.env['mrp.workorder.roll'].search([('name','like', f'{prefix}%')])
            used_numbers = []
            for r in existing_rolls:
                parts_name = r.name.split('-')
                if len(parts_name) > 1 and parts_name[1].isdigit():
                    used_numbers.append(int(parts_name[1]))
            next_number = max(used_numbers) + 1 if used_numbers else 1
            if not used_numbers:
                roll.name = f'{prefix}-{str(next_number).zfill(3)}'
                next_number += 1
            new_weight = round(roll.gross_weight - self.new_weight, 2)
            roll.copy({
                'name': f'{prefix}-{str(next_number).zfill(3)}',
                'net_weight': self.new_weight,
                'gross_weight': self.new_weight,
            })
            roll.net_weight = new_weight
            roll.gross_weight = new_weight