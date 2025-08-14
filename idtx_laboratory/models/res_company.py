from odoo import fields, models, api

class ResCompany(models.Model):
    _inherit = 'res.company'

    chemical_category_ids = fields.One2many('product.category', 'chemical_company_categ_id', string='Chemical Categories')
    weaving_category_ids = fields.One2many('product.category', 'weaving_company_categ_id', string='Weaving Categories')
    thread_category_ids = fields.One2many('product.category', 'thread_company_categ_id', string='Thread Categories')

    @api.onchange('weaving_category_ids','thread_category_ids','chemical_category_ids')
    def _onchange_weaving_thread_category(self):
        self.env['product.template'].search([])._compute_is_chemical_weaving_thread()
        
    @api.onchange('chemical_category_ids')
    def _onchange_chemical_category_ids(self):
        products = self.env['product.template'].search([('categ_id','in',self.chemical_category_ids.ids)])
        products.is_chemical = True

    def write(self, vals):
        res = super().write(vals)
        if 'chemical_category_ids' in vals:
            products = self.env['product.template'].search([('categ_id','in',self.chemical_category_ids.ids)])
            products.is_chemical = True
        if 'weaving_category_ids' in vals:
            products = self.env['product.template'].search([('categ_id','in',self.weaving_category_ids.ids)])
            products.is_weaving = True
        if 'thread_category_ids' in vals:
            products = self.env['product.template'].search([('categ_id','in',self.thread_category_ids.ids)])
            products.is_thread = True
        return res