from odoo import fields, models, api, _

class ProductTemplate(models.Model):
    _inherit = 'product.template'

    is_chemical = fields.Boolean('is_chemical', compute='_compute_is_chemical', store=True)

    @api.depends('categ_id')
    def _compute_is_chemical(self):
        company_categories = set(self.env.company.chemical_category_ids)
        for rec in self:
            category = rec.categ_id
            is_chemical = False
            while category:
                if category in company_categories:
                    is_chemical = True
                    break
                category = category.parent_id
            rec.is_chemical = is_chemical
            