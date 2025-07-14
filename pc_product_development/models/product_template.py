from odoo import fields, models, api

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
    is_weaving = fields.Boolean('is_weaving', compute='_compute_is_weaving', store=True)

    @api.depends('categ_id')
    def _compute_is_weaving(self):
        for rec in self:
            category = rec.categ_id
            rec.is_weaving = False
            while category:
                if category.is_weaving:
                    rec.is_weaving = True
                    break
                category = category.parent_id