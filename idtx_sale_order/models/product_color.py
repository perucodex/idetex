from odoo import models, fields

class ProductColor(models.Model):
    _name = 'product.color'
    _description = 'Product Color'

    name = fields.Char('Name')
    # is_lab_color = fields.Boolean('Require LabDip')
    color_range_ids = fields.Many2many('color.range', string='Color Ranges')
    color_intensity_ids = fields.Many2many('color.intensity', string='Color Intensities')
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
        index=True,
        required=True
    )