from odoo import fields, models, api

class StockLot(models.Model):
    _inherit = "stock.lot"
    
    is_thread = fields.Boolean(related='product_id.product_tmpl_id.is_thread')
    state = fields.Selection([
        ('sfe', 'Suitable for Everything'),
        ('dir', 'Directed'),
        ('ysg', 'Yarn Sale Gamarra'),
    ], string='State')
    defects = fields.Text('Defects')
    product_family_ids = fields.Many2many('product.family', string='Product Families')
    color_intensity_ids = fields.Many2many('color.intensity', string='Color Intensities')
