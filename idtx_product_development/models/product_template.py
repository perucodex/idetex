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
    is_weaving = fields.Boolean('is_weaving', compute='_compute_is_weaving_thread', store=True)
    is_thread = fields.Boolean('is_thread', compute='_compute_is_weaving_thread', store=True)

    @api.model
    @api.depends('categ_id')
    def _compute_is_weaving_thread(self):
        for rec in self:
            rec.is_weaving = True if rec.categ_id in self.env.company.weaving_category_ids else False
            rec.is_thread = True if rec.categ_id in self.env.company.thread_category_ids else False