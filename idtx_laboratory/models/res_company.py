from odoo import fields, models, api

class ResCompany(models.Model):
    _inherit = 'res.company'

    chemical_category_ids = fields.One2many('product.category', 'chemical_company_categ_id', string='Chemical Categories')
   
    def write(self, vals):
        res = super().write(vals)
        if 'chemical_category_ids' in vals:
            all_products = self.env['product.template'].search([])
            products = self.env['product.template'].search([('categ_id','child_of',self.chemical_category_ids.ids)])
            products.is_chemical = True
            diff = all_products - products
            diff.is_chemical = False
        return res