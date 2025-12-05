from odoo import models, fields

class HrAfp(models.Model):
    _name = 'hr.afp'
    _description = 'AFP'

    name = fields.Char(string='Name')
    afp_contribution = fields.Float(string='Contribution (%)', default=0.10)
    commission_balance = fields.Float(string='Commission on Balance (%)')
    commission_flow = fields.Float(string='Commission on Flow (%)')
    insurance_rate = fields.Float(string='Insurance (%)')
    max_insurable = fields.Float('Max. Insurable Remuneration')