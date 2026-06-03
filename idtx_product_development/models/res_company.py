from odoo import fields, models, api

class ResCompany(models.Model):
    _inherit = 'res.company'

    # Many2many: una misma categoria puede ser de tejido/hilado en VARIAS
    # companias (p. ej. idetex y fullpima a la vez). Antes eran One2many
    # (Many2one en product.category), por eso una categoria solo podia estar
    # en una compania. La migracion copia el dato anterior.
    weaving_category_ids = fields.Many2many(
        'product.category', relation='company_weaving_category_rel',
        column1='company_id', column2='category_id', string='Weaving Categories')
    thread_category_ids = fields.Many2many(
        'product.category', relation='company_thread_category_rel',
        column1='company_id', column2='category_id', string='Thread Categories')

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