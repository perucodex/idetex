# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError

class MrpProduction(models.Model):
    _inherit = 'mrp.production'

    def _roll_qty_sync_targets(self):
        return self.filtered(lambda p: p.product_id and p.product_id.is_weaving)

    def _set_quantities(self):
        """Normalize picked/lot flags before running Odoo standard checks.

        In weaving manual consumption, users may set component lines with lot/qty
        but `move.picked` can remain False, triggering the standard
        "not move.picked" error path.
        """
        for production in self._roll_qty_sync_targets():
            tracked_moves = production.move_raw_ids.filtered(
                lambda m: m.manual_consumption and m.has_tracking in ('serial', 'lot') and m.state not in ('done', 'cancel')
            )
            for move in tracked_moves:
                has_picked_line = False
                for line in move.move_line_ids.filtered(lambda l: l.quantity):
                    if not line.lot_id and line.quant_id and line.quant_id.lot_id:
                        line.lot_id = line.quant_id.lot_id
                    elif not line.lot_id and line.lot_name:
                        lot = self.env['stock.lot'].search([
                            ('name', '=', line.lot_name),
                            ('product_id', '=', line.product_id.id),
                            '|',
                            ('company_id', '=', line.company_id.id),
                            ('company_id', '=', False),
                        ], limit=1)
                        if lot:
                            line.lot_id = lot

                    if line.lot_id:
                        line.picked = True
                        has_picked_line = True

                if has_picked_line:
                    move.picked = True

        return super()._set_quantities()

    @api.onchange('production_type')
    def _onchange_production_type(self):
        for rec in self:
            if rec.bom_id.technical_sheet_id.production_state == 'Production' and rec.production_type == 'pilot':
                raise UserError(_('Product is in Production state!'))
            elif rec.bom_id.technical_sheet_id.production_state == 'Pilot' and rec.production_type == 'sample':
                raise UserError(_('Product is in Pilot state'))

    def button_mark_done(self):
        res = super().button_mark_done()
        for rec in self:
            if not rec.production_type:
                raise UserError(_('Please select a production type before marking as done.'))
            if rec.production_type == 'sale' or rec.production_type == 'service':
                prod_state = 'Production'
            elif rec.production_type == 'pilot':
                prod_state = 'Pilot'
            elif rec.production_type == 'sample':
                prod_state = 'Sample'
            rec.bom_id.technical_sheet_id.production_state = prod_state
        return res