from odoo import models

class StockQuant(models.Model):
    _inherit = 'stock.quant'

    def reprint(self):
        for rec in self:
            if rec.lot_id and rec.lot_id.roll_id:
                roll = rec.lot_id.roll_id
                roll._print_zpl_to_network(roll.create_zpl(rec.quantity))  