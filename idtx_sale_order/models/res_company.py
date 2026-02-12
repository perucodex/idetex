from odoo import fields, models, api

class ResCompany(models.Model):
    _inherit = 'res.company'

    max_discount = fields.Float('Max. Discount', default=0.05)