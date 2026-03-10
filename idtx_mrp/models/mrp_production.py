# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.fields import Command
from odoo.exceptions import UserError

class MrpProduction(models.Model):
    _inherit = 'mrp.production'

    batch_id = fields.Many2one('mrp.workorder.batch', string='Batch')
    roll_ids = fields.One2many('mrp.production.roll', 'production_id', string='Rolls')
    production_type = fields.Selection([
        ('sale', 'Sale'),
        ('service', 'Service'),
        ('pilot', 'Pilot'),
        ('sample', 'Sample'),
    ], string='Production Type')

    @api.depends('bom_id', 'product_id', 'product_qty', 'product_uom_id', 'never_product_template_attribute_value_ids')
    def _compute_workorder_ids(self):
        res = super()._compute_workorder_ids()
        for rec in self:
            for wo in rec.workorder_ids:
                wo.mrwo_id = wo.operation_id.operation_id
        return res

    def button_mark_done(self):
        new_lines = []
        new_lots = []
        if len(self.finished_move_line_ids) == 1:
            delete_line = self.finished_move_line_ids
            for roll in self.roll_ids:
                new_lines += delete_line.copy({'quantity': roll.gross_weight, 'lot_id': roll.lot_id.id, 'packaging_uom_qty': roll.gross_weight})
                new_lots += roll.lot_id
            self.finished_move_line_ids = [Command.link(l.id) for l in new_lines]
            if not self.roll_ids:
                raise UserError(_("No rolls defined for this production. Please add at least one roll to proceed."))
            self.product_qty = sum(self.roll_ids.mapped('gross_weight'))
            delete_line.unlink()
        return super().button_mark_done()