from odoo import models, fields

class ResCompany(models.Model):
    _inherit = 'res.company'

    is_company_produce = fields.Boolean('Production Company', store=True)