from odoo import fields, models

class ProductTemplate(models.Model):
    _inherit = 'product.template'

    density = fields.Integer('Density')
    width = fields.Float('Width')
    gauge = fields.Integer('Gauge')
    first_wash_shrinkage = fields.Char('First Wash Shrinkage')
    first_wash_twist = fields.Char('First Wash Twist')
    yield_meter = fields.Integer('Yield')
    scrap = fields.Float('Scrap')
    weave_type = fields.Selection([
        ('open', 'Open'),
        ('tubular', 'Tubular'),
    ], string='Weave Type')
    batch = fields.Char('Batch')
    memo = fields.Text('Memo')