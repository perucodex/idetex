from odoo import models, fields

class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    pension_system = fields.Selection([
        ('onp', 'ONP'),
        ('afp', 'AFP'),
    ], string="Pension Sistem", default='onp')
    afp_id = fields.Many2one('hr.afp', string='AFP')
    commission_type = fields.Selection([
        ('balance', 'On Balance'),
        ('flow', 'On Flow'),
    ], string='Commission Type', default='balance')