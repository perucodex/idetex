from odoo import fields, models


class ApprovalProductLine(models.Model):
    _inherit = 'approval.product.line'

    sequence = fields.Integer('Sequence')
    item = fields.Integer('Item', compute='_compute_item')

    def _compute_item(self):
        for rec in self:
            rec.item = rec.sequence + 1