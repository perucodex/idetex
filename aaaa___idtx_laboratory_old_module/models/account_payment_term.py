from odoo import fields, models, api

class AccountPaymentTerm(models.Model):
    _inherit = 'account.payment.term'

    financial_percentage = fields.Float('Financial Percentage')