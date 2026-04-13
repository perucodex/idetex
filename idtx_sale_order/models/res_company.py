from odoo import fields, models, api

class ResCompany(models.Model):
    _inherit = 'res.company'

    max_discount = fields.Float('Max. Discount', default=0.05)
    sales_pricelist_id = fields.Many2one(
        'product.pricelist',
        string='Sales Pricelist',
        domain="[('company_id', 'in', [False, id])]",
        help='Pricelist used as the pricing source for all sale orders in this company.',
    )