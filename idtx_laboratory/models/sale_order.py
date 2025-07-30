from odoo import models, fields, Command, api, _

class SaleOrder(models.Model):
    _inherit = 'sale.order'
    
    lab_dev_id = fields.Many2one('lab.dev', string='Lab Dev')
    weaving_warning = fields.Text('weaving_warning', compute='_compute_weaving_warning')

    @api.onchange('payment_term_id','incoterm')
    def _onchange_payment_term_id(self):
        self.order_line._compute_price_unit()

    # def action_update_taxes(self):
    #     res = super().action_update_taxes()
    #     self.order_line._compute_price_unit()
    #     return res

    def action_confirm(self):
        res = super().action_confirm()

        LabDev = self.env['lab.dev']
        today = fields.Date.context_today(self)
        # Crear una sola lab.dev para la orden
        lab_dev = LabDev.create({
            'lab_dev_date': today,
            'sale_order_id': self.id,
            'lab_dev_line_ids': [Command.create({
                 'product_id': line.product_id.id,
                 'color_name': line.product_color_id.name,
            }) for line in self.order_line]
        })

        self.lab_dev_id = lab_dev

        return res
    
    @api.depends('order_line')
    def _compute_weaving_warning(self):
        for order in self:
            order.weaving_warning = ''
            for line in order.order_line:
                if line.product_template_id.bom_ids:
                    bom_id = line.product_template_id.bom_ids[0]
                    for bom_line in bom_id.bom_line_ids:
                        pricelist_item_id = line.order_id.pricelist_id._get_product_rule(
                            bom_line.product_id,
                            quantity=bom_line.product_qty or 1.0,
                            uom=bom_line.product_uom_id,
                            date=line._get_order_date(),
                        )
                        if not pricelist_item_id:
                            order.weaving_warning += _(('Product %s has product %s on its bom and does not have a price in %s price list. The price is obtained from its own sale price.') %( line.product_id.name, bom_line.product_id.name, order.pricelist_id.name)) + '\n'
                    for operation in bom_id.operation_ids:
                        if operation.operation_id.type_prices == 'col':
                            operation_color_line = operation.operation_id.product_color_price_ids.search([('product_color_id','=',line.product_color_id.id),('mrwo_id','=', operation.operation_id.id)])
                            if not operation_color_line:
                                order.weaving_warning += (_('The type prices of %s operation is by color. The color %s does not exists in the operation color list of product %s.') %(operation.operation_id.name, line.product_color_id.name, line.product_id.name)) + '\n'