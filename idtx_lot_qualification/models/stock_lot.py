from odoo import fields, models, api

class StockLot(models.Model):
    _inherit = 'stock.lot'
    
    is_thread = fields.Boolean(related='product_id.product_tmpl_id.is_thread')
    state = fields.Selection([
        ('sfe', 'Suitable for Everything'),
        ('dir', 'Directed'),
        ('ysg', 'Yarn Sale Gamarra'),
    ], string='State')
    defects = fields.Text('Defects')
    product_family_ids = fields.Many2many('product.family', string='Product Families')
    color_intensity_ids = fields.Many2many('color.intensity', string='Color Intensities')
    lot_detail_ids = fields.One2many('stock.lot.detail', 'lot_id', string='Lot Detail')

class StockLotDetail(models.Model):
    _name = 'stock.lot.detail'
    _description = 'Stock Lot Detail'

    lot_id = fields.Many2one('stock.lot', string='Lot')
    weight = fields.Float('Weight')
    bags = fields.Integer('Bags')
    cones = fields.Integer('Cones')