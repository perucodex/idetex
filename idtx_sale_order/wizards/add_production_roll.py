from odoo import models

class BatchAddWizard(models.TransientModel):
    _inherit = 'batch.add.wizard'

    def _get_lot_vals(self, prd, line):
        res = super()._get_lot_vals(prd, line)
        res.append({'color_recipe_id': prd.color_recipe_id.id})
        return res
