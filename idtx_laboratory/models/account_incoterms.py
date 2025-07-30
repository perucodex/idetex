from odoo import fields, models, api

class AccountIncoterms(models.Model):
    _inherit = 'account.incoterms'

    currency_id = fields.Many2one('res.currency', string='Currency', default=lambda self: self.env.ref('base.USD').id)
    unit_price = fields.Monetary('Unit Price',currency_field='currency_id')