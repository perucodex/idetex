from odoo import api, fields, models, _
from odoo.exceptions import UserError

class ProductCategory(models.Model):
    _inherit = 'product.category'

    chemical_company_categ_id = fields.Many2one('res.company', string='chemical_company_categ_id')
    weaving_company_categ_id = fields.Many2one('res.company', string='weaving_company_categ_id')
    thread_company_categ_id = fields.Many2one('res.company', string='thread_company_categ_id')