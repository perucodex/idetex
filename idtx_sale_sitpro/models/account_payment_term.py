from odoo import fields, models

class AccountPaymentTerm(models.Model):
    _inherit = 'account.payment.term'

    sitpro_code = fields.Char('Sitpro Code')