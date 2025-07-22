from odoo import fields, models, api

class ProductTemplate(models.Model):
    _inherit = 'product.template'

    is_chemical = fields.Boolean('is_chemical', compute='_compute_is_chemical_thread', store=True)

    @api.depends('categ_id')
    def _compute_is_chemical_thread(self):
        for rec in self:
            rec.is_chemical = True if rec.categ_id in self.env.company.chemical_category_ids else False