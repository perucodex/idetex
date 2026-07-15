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
                if rec.state == 'done':
                    rec.quantity = sum(rec.roll_ids.mapped('quantity'))
                    rec.roll_weight = sum(rec.roll_ids.mapped('gross_weight'))
                    rec.progress = 100
                else:
                    # El avance se mide contra el TOTAL de la OF
                    # (qty_production); qty_remaining disminuye con el avance
                    # e inflaba el porcentaje.
                    if rec.weave_type == 'rect':
                        rec.quantity = sum(rec.roll_ids.mapped('quantity'))
                        rec.progress = (rec.quantity / rec.qty_production * 100) if rec.qty_production else 0
                        rec.roll_weight = 0
                    else:
                        rec.roll_weight = sum(rec.roll_ids.mapped('gross_weight'))
                        rec.progress = (rec.roll_weight / rec.qty_production * 100) if rec.qty_production else 0
                        rec.quantity = 0
            elif rec.operation_type in rec.BATCH_OPERATION_TYPES:
                if rec.batch_ids:
                    # Solo los rollos de la partida que pertenecen a ESTA OF
                    # (las partidas pueden combinar rollos de varias OFs).
                    batch_rolls = rec.batch_ids.wo_roll_ids.filtered(
                        lambda r: r.workorder_id and r.workorder_id.production_id == rec.production_id
                    )
                    if rec.state == 'done':
                        rec.quantity = sum(rec.roll_ids.mapped('quantity'))
                        rec.roll_weight = sum(rec.roll_ids.mapped('gross_weight'))
                        rec.progress = 100
                    else:
                        if sum(batch_rolls.mapped('gross_weight')) > 0:
                            rec.roll_weight = sum(batch_rolls.mapped('gross_weight'))
                            rec.progress = (rec.roll_weight / rec.qty_production * 100) if rec.qty_production else 0
                            rec.quantity = 0
                        else:
                            rec.quantity = sum(batch_rolls.mapped('quantity'))
                            rec.progress = (rec.quantity / rec.qty_production * 100) if rec.qty_production else 0
                            rec.roll_weight = 0
                else:
                    rec.quantity = 0
                    rec.roll_weight = 0
                    rec.progress = 0
            else:
                rec.quantity = 0
                rec.roll_weight = 0
                rec.progress = 0
        
    def get_available_sizes(self):
        '''Devuelve las tallas (size_chart_ids) del producto relacionado'''
        self.ensure_one()
        sizes = self.production_id.bom_id.technical_sheet_id.size_chart_ids
        return [{'id': s.id, 'size': s.size} for s in sizes]