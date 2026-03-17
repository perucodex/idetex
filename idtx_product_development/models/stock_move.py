from odoo import models, api

class StockMove(models.Model):
    _inherit = 'stock.move'

    @api.depends('raw_material_production_id.qty_producing', 'product_uom_qty', 'product_uom')
    def _compute_should_consume_qty(self):
        res = super()._compute_should_consume_qty()
        for move in self:
            mo = move.raw_material_production_id
            if not mo or not move.product_uom:
                move.should_consume_qty = 0
                continue
            if mo.product_id and mo.product_id.is_weaving:
                # For weaving products, we want to consume based on the quantity of rolls produced, not the quantity of the MO.
                # This is because the MO quantity may not reflect the actual output if rolls are used.
                move.should_consume_qty = move.product_uom.round(mo._roll_done_qty() * move.unit_factor)
        return res