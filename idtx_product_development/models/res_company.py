from odoo import fields, models, api

class ResCompany(models.Model):
    _inherit = 'res.company'

    weaving_category_ids = fields.One2many('product.category', 'weaving_company_categ_id', string='Weaving Categories')
    thread_category_ids = fields.One2many('product.category', 'thread_company_categ_id', string='Thread Categories')

    def write(self, vals):
        res = super().write(vals)
        all_products = self.env['product.template'].search([])
        if 'weaving_category_ids' in vals:
            products = self.env['product.template'].search([('categ_id','child_of',self.weaving_category_ids.ids)])
            products.is_weaving = True
            diff = all_products - products
            diff.is_weaving = False
        if 'thread_category_ids' in vals:
            products = self.env['product.template'].search([('categ_id','in',self.thread_category_ids.ids)])
            products.is_thread = True
            diff = all_products - products
            diff.is_thread = False
        return res