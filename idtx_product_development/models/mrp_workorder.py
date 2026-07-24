from odoo import models, fields, api

class MrpWorkorder(models.Model):
    _inherit = 'mrp.workorder'

    weave_type = fields.Selection(related='product_id.product_tmpl_id.analysis_id.weave_type', store=True)
    roll_weight = fields.Float('Roll Weight', compute='_compute_progress')
    quantity = fields.Float('Quantity LAB', compute='_compute_progress')
    progress = fields.Float('Progress', compute='_compute_progress')

    @api.depends(
        'roll_ids',
        'roll_ids.transfer_state',
        'state',
        'batch_ids',
        'batch_ids.wo_roll_ids',
        'batch_ids.wo_roll_ids.gross_weight',
        'batch_ids.wo_roll_ids.quantity',
        'batch_ids.wo_roll_ids.workorder_id',
        'batch_ids.wo_roll_ids.workorder_id.production_id',
        'batch_ids.child_batch_ids.wo_roll_ids',
    )
    def _compute_progress(self):
        for rec in self:
            if rec.operation_type == 'weaving':
                # AVANCE = salida de esta OT: EXCLUYE los TRANSFERIDOS (se fueron
                # a otra OT) e INCLUYE los RECIBIDOS (el destino sí los produce).
                wrolls = rec.roll_ids.filtered(lambda r: r.transfer_state != 'transferido')
                if rec.state == 'done':
                    rec.quantity = sum(wrolls.mapped('quantity'))
                    rec.roll_weight = sum(wrolls.mapped('gross_weight'))
                    rec.progress = 100
                else:
                    # El avance se mide contra el TOTAL de la OF
                    # (qty_production); qty_remaining disminuye con el avance
                    # e inflaba el porcentaje.
                    if rec.weave_type == 'rect':
                        rec.quantity = sum(wrolls.mapped('quantity'))
                        rec.progress = (rec.quantity / rec.qty_production * 100) if rec.qty_production else 0
                        rec.roll_weight = 0
                    else:
                        rec.roll_weight = sum(wrolls.mapped('gross_weight'))
                        rec.progress = (rec.roll_weight / rec.qty_production * 100) if rec.qty_production else 0
                        rec.quantity = 0
            elif rec.operation_type in rec.BATCH_OPERATION_TYPES:
                if rec.batch_ids:
                    # Mismo conjunto de rollos que la cantidad producida
                    # (`_get_textile_rolls`): resuelve divisiones y EXCLUYE
                    # partidas con reproceso pendiente, así el % de avance baja
                    # al reabrir y se recupera al re-registrar.
                    batch_rolls = rec._get_textile_rolls()
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