from odoo import fields, models

class StockQuant(models.Model):
    _inherit = 'stock.quant'

    batch_id = fields.Many2one(
        related='lot_id.batch_id', string='Partida', store=True, index=True,
        help='Partida del rollo (desde el lote): permite agrupar y filtrar el stock por partida.')
    quality_grade = fields.Selection(
        related='lot_id.quality_grade', string='Grado', store=True, index=True)

    def reprint(self):
        for rec in self:
            if rec.lot_id and rec.lot_id.roll_id:
                roll = rec.lot_id.roll_id
                if self.env.company.is_printer:
                    roll._print_zpl_to_network(roll.create_zpl(rec.quantity), self.env.company.zpl_printer_ip)  
    
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