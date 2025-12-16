from odoo import models, fields

class ResCompany(models.Model):
    _inherit = 'res.company'

    life_insurance_law = fields.Float('Life Insurance Law')