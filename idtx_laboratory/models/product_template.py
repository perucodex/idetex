from odoo import fields, models, api, _

class ProductTemplate(models.Model):
    _inherit = 'product.template'

    is_chemical = fields.Boolean('is_chemical', compute='_compute_is_chemical', store=True)

    @api.depends('categ_id')
    def _compute_is_chemical(self):
        for rec in self:
            rec.is_chemical = True if rec.categ_id in self.env.company.chemical_category_ids else False
            