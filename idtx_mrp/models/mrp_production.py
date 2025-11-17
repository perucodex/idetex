# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.fields import Command
from odoo.exceptions import UserError

class MrpProduction(models.Model):
    _inherit = 'mrp.production'

    batch_id = fields.Many2one('mrp.workorder.batch', string='Batch')
    roll_ids = fields.One2many('mrp.production.roll', 'production_id', string='Rolls')

    @api.depends('bom_id', 'product_id', 'product_qty', 'product_uom_id', 'never_product_template_attribute_value_ids')
    def _compute_workorder_ids(self):
        res = super()._compute_workorder_ids()
        for rec in self:
            for wo in rec.workorder_ids:
                wo.mrwo_id = wo.operation_id.operation_id
        return res
    
    # def _prepare_stock_lot_values(self):
    #     '''Heredamos la funcion para que el lote se cree desde la partida de rollos tejidos'''
    #     self.ensure_one()
    #     res = super()._prepare_stock_lot_values()
    #     if self.product_id.product_tmpl_id.is_weaving:
    #         if not self.batch_id:
    #             raise UserError(_("Please set the first Batch Number for production"))
    #         else:
    #             res['name'] = self.batch_id.name
    #     return res

    def button_mark_done(self):
        new_lines = []
        new_lots = []
        if len(self.finished_move_line_ids) == 1:
            delete_line = self.finished_move_line_ids
            for roll in self.roll_ids:
                # lot = self.env['stock.lot'].create({'name': roll.batch_id.name + '-' + str(counter + 1).zfill(3), 'product_id': delete_line.product_id.id})
                new_lines += delete_line.copy({'quantity': roll.gross_weight, 'lot_id': roll.lot_id.id, 'packaging_uom_qty': roll.gross_weight})
                new_lots += roll.lot_id
            self.finished_move_line_ids = [Command.link(l.id) for l in new_lines]
            self.product_qty = sum(self.roll_ids.mapped('gross_weight'))
            delete_line.unlink()
        res = super().button_mark_done()
        # if new_lots:
        #     self.lot_producing_ids = [Command.link(l.id) for l in new_lots]
        return res