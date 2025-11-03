from odoo import api, fields, models

class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    currency_rate_usd = fields.Float(
        string="Currency Rate USD",
        compute='_compute_currency_rate_usd',
        digits=0,
        store=True,
        precompute=True,
    )

    @api.depends('currency_id', 'date_order', 'company_id')
    def _compute_currency_rate_usd(self):
        usd_currency = self.env.ref('base.USD')
        for order in self:
            order.currency_rate_usd = self.env['res.currency']._get_conversion_rate(
                from_currency=usd_currency,
                to_currency=order.company_id.currency_id,
                company=order.company_id,
                date=(order.date_order or fields.Datetime.now()).date(),
            )