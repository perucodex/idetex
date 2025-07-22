from odoo import fields, models, api

class ResCompany(models.Model):
    _inherit = 'res.company'

    weaving_category_ids = fields.One2many('product.category', 'weaving_company_categ_id', string='Weaving Categories')
    thread_category_ids = fields.One2many('product.category', 'thread_company_categ_id', string='Thread Categories')