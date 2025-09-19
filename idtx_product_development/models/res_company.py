from odoo import fields, models, api

class ResCompany(models.Model):
    _inherit = 'res.company'

    weaving_category_ids = fields.One2many('product.category', 'weaving_company_categ_id', string='Weaving Categories')
    thread_category_ids = fields.One2many('product.category', 'thread_company_categ_id', string='Thread Categories')

    def write(self, vals):
        res = super().write(vals)
        if 'weaving_category_ids' in vals:
            products = self.env['product.template'].search([('categ_id','in',self.weaving_category_ids.ids),('company_id','=', self.id)])
            products.is_weaving = True
        if 'thread_category_ids' in vals:
            products = self.env['product.template'].search([('categ_id','in',self.thread_category_ids.ids),('company_id','=', self.id)])
            products.is_thread = True
        return res