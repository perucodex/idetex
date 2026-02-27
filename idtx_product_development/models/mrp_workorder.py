from odoo import models, fields, api

class MrpWorkorder(models.Model):
    _inherit = 'mrp.workorder'

    weave_type = fields.Selection(related='product_id.product_tmpl_id.analysis_id.weave_type', store=True)
    roll_weight = fields.Float('Roll Weight', compute='_compute_progress')
    quantity = fields.Float('Quantity LAB', compute='_compute_progress')
    progress = fields.Float('Progress', compute='_compute_progress')

    @api.depends(
        'roll_ids',
        'batch_ids',
        'batch_ids.wo_roll_ids',
        'batch_ids.wo_roll_ids.gross_weight',
        'batch_ids.wo_roll_ids.quantity',
        'batch_ids.wo_roll_ids.workorder_id',
        'batch_ids.wo_roll_ids.workorder_id.production_id',
    )
    def _compute_progress(self):
        for rec in self:
            if rec.operation_type == 'weaving':
                if rec.weave_type == 'rect':
                    rec.quantity = sum(rec.roll_ids.mapped('quantity'))
                    rec.progress = (rec.quantity / (rec.qty_remaining if rec.qty_remaining else rec.qty_production)) * 100
                    rec.roll_weight = 0
                else:
                    rec.roll_weight = sum(rec.roll_ids.mapped('gross_weight'))
                    rec.progress = (rec.roll_weight / (rec.qty_remaining if rec.qty_remaining else rec.qty_production)) * 100
                    rec.quantity = 0
            elif rec.operation_type == 'dyeing':
                if rec.batch_ids:
                    batch_rolls = rec.batch_ids.wo_roll_ids.filtered(
                        lambda r: r.workorder_id and r.workorder_id.production_id == rec.production_id
                    )
                    if sum(batch_rolls.mapped('gross_weight')) > 0:
                        rec.roll_weight = sum(batch_rolls.mapped('gross_weight'))
                        if rec.state not in ('done', 'cancel'):
                            rec.qty_produced = rec.roll_weight
                        rec.progress = (rec.roll_weight / (rec.qty_remaining if rec.qty_remaining else rec.qty_production)) * 100
                        rec.quantity = 0
                    else:
                        rec.quantity = sum(batch_rolls.mapped('quantity'))
                        if rec.state not in ('done', 'cancel'):
                            rec.qty_produced = rec.quantity
                        rec.progress = (rec.quantity / (rec.qty_remaining if rec.qty_remaining else rec.qty_production)) * 100
                        rec.roll_weight = 0
                else:
                    rec.quantity = 0
                    if rec.state not in ('done', 'cancel'):
                        rec.qty_produced = 0
                    rec.roll_weight = 0
                    rec.progress = 0
            else:
                rec.quantity = 0
                if rec.state not in ('done', 'cancel'):
                    rec.qty_produced = 0
                rec.roll_weight = 0
                rec.progress = 0
        
    def get_available_sizes(self):
        '''Devuelve las tallas (size_chart_ids) del producto relacionado'''
        self.ensure_one()
        sizes = self.production_id.bom_id.technical_sheet_id.size_chart_ids
        return [{'id': s.id, 'size': s.size} for s in sizes]