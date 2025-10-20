from odoo import  api, models

class PurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'

    @api.model
    def _prepare_purchase_order_line(self, product_id, product_qty, product_uom, company_id, partner_id, po):
        res = super()._prepare_purchase_order_line(product_id, product_qty, product_uom, company_id, partner_id, po)
        res['name'] = self.env.context.get('name') if res['name'] != self.env.context.get('name') else res['name']
        return res
