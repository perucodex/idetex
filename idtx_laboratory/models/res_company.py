from odoo import fields, models, api

class ResCompany(models.Model):
    _inherit = 'res.company'

    chemical_category_ids = fields.One2many('product.category', 'chemical_company_categ_id', string='Chemical Categories')
    weaving_category_ids = fields.One2many('product.category', 'weaving_company_categ_id', string='Weaving Categories')
    thread_category_ids = fields.One2many('product.category', 'thread_company_categ_id', string='Thread Categories')

    @api.onchange('weaving_category_ids','thread_category_ids','chemical_category_ids')
    def _onchange_weaving_thread_category(self):
        self.env['product.template'].search([])._compute_is_chemical_weaving_thread()