from odoo import models

class StockQuant(models.Model):
    _inherit = 'stock.quant'

    def reprint(self):
        for rec in self:
            if rec.lot_id and rec.lot_id.roll_id:
                roll = rec.lot_id.roll_id
                roll._print_zpl_to_network(roll.create_zpl(rec.quantity))  
    
    def split_quant(self, quantity):
        # Dividir quant
        self.inventory_quantity = self.inventory_quantity - quantity
        quant = StockQuant.create({
            'product_id': self.product_id.id,
            'location_id': self.location_id.id,
            'inventory_quantity': float(quantity),
            'lot_id': self.lot_id.id,
        })
        quant.action_apply_inventory()
        self.action_apply_inventory()