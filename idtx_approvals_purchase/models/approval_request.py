from odoo import models, _

class ApprovalRequest(models.Model):
    _inherit = 'approval.request'

    # OVERRIDE para que haga el filtro y se puedan repetir los productos
    # por descripción
    def _create_purchase_orders(self):
        self.product_line_ids._check_products_vendor()
        for line in self.product_line_ids:
            seller = line.seller_id or line.product_id.with_company(line.company_id)._select_seller(
                quantity=line.po_uom_qty,
                uom_id=line.product_id.uom_id,
            )
            vendor = seller.partner_id
            po_domain = line._get_purchase_orders_domain(vendor)
            purchase_orders = self.env['purchase.order'].search(po_domain)

            if purchase_orders:
                # Existing RFQ found: check if we must modify an existing
                # purchase order line or create a new one.
                purchase_line = self.env['purchase.order.line'].search([
                    ('order_id', 'in', purchase_orders.ids),
                    ('name', '=', line.description),
                    ('product_id', '=', line.product_id.id),
                    ('product_uom_id', '=', line.seller_id.product_uom_id.id or line.product_id.uom_id.id),
                ], limit=1)
                purchase_order = self.env['purchase.order']
                if purchase_line:
                    # Compatible po line found, only update the quantity.
                    line.purchase_order_line_id = purchase_line.id
                    purchase_line.product_qty += line.po_uom_qty
                    purchase_order = purchase_line.order_id
                else:
                    # No purchase order line found, create one.
                    purchase_order = purchase_orders[0]
                    seller_uom_qty = line.product_uom_id._compute_quantity(line.quantity, seller.product_uom_id)
                    po_line_vals = self.env['purchase.order.line'].with_context(name=line.description)._prepare_purchase_order_line(
                        line.product_id,
                        seller_uom_qty,
                        seller.product_uom_id,
                        line.company_id,
                        vendor,
                        purchase_order,
                    )
                    new_po_line = self.env['purchase.order.line'].create(po_line_vals)
                    line.purchase_order_line_id = new_po_line.id
                    purchase_order.order_line = [(4, new_po_line.id)]

                # Add the request name on the purchase order `origin` field.
                new_origin = set([self.name])
                if purchase_order.origin:
                    missing_origin = new_origin - set(purchase_order.origin.split(', '))
                    if missing_origin:
                        purchase_order.write({'origin': purchase_order.origin + ', ' + ', '.join(missing_origin)})
                else:
                    purchase_order.write({'origin': ', '.join(new_origin)})
            else:
                # No RFQ found: create a new one.
                po_vals = line._get_purchase_order_values(vendor)
                new_purchase_order = self.env['purchase.order'].create(po_vals)
                seller_uom_qty = line.product_uom_id._compute_quantity(line.quantity, seller.product_uom_id)
                po_line_vals = self.env['purchase.order.line'].with_context(name=line.description)._prepare_purchase_order_line(
                    line.product_id,
                    seller_uom_qty,
                    seller.product_uom_id,
                    line.company_id,
                    vendor,
                    new_purchase_order,
                )
                new_po_line = self.env['purchase.order.line'].create(po_line_vals)
                line.purchase_order_line_id = new_po_line.id
                new_purchase_order.order_line = [(4, new_po_line.id)]
