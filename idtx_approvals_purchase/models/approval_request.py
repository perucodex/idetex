from odoo import models, _

class ApprovalRequest(models.Model):
    _inherit = 'approval.request'

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

            purchase_order = purchase_orders and purchase_orders[0] or False

            # === Construir el name esperado (igual que lo que tendrá la PO line) ===
            product_lang = line.product_id.with_prefetch().with_context(
                lang=(line.company_id and line.approval_request_id.partner_id.lang) or self.env.user.lang,
                partner_id=(line.approval_request_id.partner_id.id if line.approval_request_id and line.approval_request_id.partner_id else None),
            )
            product_lang = product_lang.with_context(seller_id=getattr(seller, 'id', False))
            base_name = (product_lang.display_name or '').strip()
            prod_purchase_desc = (product_lang.description_purchase or '').strip()
            approval_desc = (line.description or '').strip()

            # === Lógica de comparación ===
            # Si la descripción del approval es igual al nombre del producto o está vacía → no enviar nada (Odoo agrupa)
            if not approval_desc or approval_desc == line.product_id.name.strip():
                expected_name = False
            # Si la descripción es distinta de la del producto y distinta de la descripción de compra → agregarla
            elif approval_desc != prod_purchase_desc:
                expected_name = (base_name + '\n' + approval_desc).strip()
            else:
                expected_name = base_name.strip()

            # === Buscar PO line que coincida ===
            purchase_line = False
            if purchase_order:
                domain = [
                    ('order_id', '=', purchase_order.id),
                    ('product_id', '=', line.product_id.id),
                    ('product_uom_id', '=', (line.seller_id.product_uom_id.id or line.product_id.uom_id.id)),
                ]
                if expected_name:
                    # Si tiene descripción distinta → solo agrupa si name coincide exactamente
                    domain.append(('name', '=', expected_name))
                else:
                    # Si expected_name es False → agrupar por producto (sin mirar name)
                    pass
                purchase_line = self.env['purchase.order.line'].search(domain, limit=1)

            if purchase_line:
                line.purchase_order_line_id = purchase_line.id
                purchase_line.product_qty += line.po_uom_qty
            else:
                if not purchase_order:
                    po_vals = line._get_purchase_order_values(vendor)
                    purchase_order = self.env['purchase.order'].create(po_vals)

                seller_uom_qty = line.product_uom_id._compute_quantity(line.quantity, seller.product_uom_id)
                po_line_vals = self.env['purchase.order.line']._prepare_purchase_order_line(
                    line.product_id,
                    seller_uom_qty,
                    seller.product_uom_id,
                    line.company_id,
                    vendor,
                    purchase_order,
                )

                # 👉 Solo forzar el name si expected_name tiene valor
                if expected_name:
                    po_line_vals['name'] = expected_name

                new_po_line = self.env['purchase.order.line'].create(po_line_vals)
                line.purchase_order_line_id = new_po_line.id
                purchase_order.order_line = [(4, new_po_line.id)]

            # === Actualizar origin de la PO ===
            new_origin = set([self.name])
            if purchase_order.origin:
                missing_origin = new_origin - set(purchase_order.origin.split(', '))
                if missing_origin:
                    purchase_order.write({'origin': purchase_order.origin + ', ' + ', '.join(missing_origin)})
            else:
                purchase_order.write({'origin': ', '.join(new_origin)})
