from odoo import models, fields, Command, api, _

class SaleOrder(models.Model):
    _inherit = 'sale.order'
    
    lab_dev_id = fields.Many2one('lab.dev', string='Lab Dev')
    weaving_warning = fields.Text('weaving_warning', compute='_compute_weaving_warning')
    sale_order_id = fields.Many2one('sale.order', string='Sale Order')
    quotation_id = fields.Many2one('sale.order', string='Quotation')
    applicant_id = fields.Many2one('res.partner', string='Applicant')
    sale_type = fields.Selection([
        ('sale', 'Sale'),
        ('service', 'Service'),
    ], string='Sale Type', default='sale')

    @api.onchange('sale_type')
    def _onchange_sale_type(self):
        for rec in self:
            rec.order_line._onchange_product_or_color()
            rec.order_line._onchange_bom_id()

    @api.onchange('payment_term_id','incoterm')
    def _onchange_payment_term_id(self):
        self.order_line._compute_price_unit()

    def create_labdev(self):
        LabDev = self.env['lab.dev']
        today = fields.Date.context_today(self)
        # Crear una sola lab.dev para la orden
        data = {
            'lab_dev_date': today,
            'sale_order_id': self.id,
            'lab_dev_line_ids': [Command.create({
                 'product_id': line.product_template_id.id,
                 'color_name': line.product_color_id.name,
                 'sale_order_line_id': line.id,
            }) for line in self.order_line.filtered(lambda l: l.product_template_id.is_weaving)]
        }
        lab_dev = LabDev.create(data)
        self.lab_dev_id = lab_dev
        self.open_labdev()
    
    def open_labdev(self):
        return self.lab_dev_id._get_records_action(name=_("Lab Dev"))
    
    @api.depends('order_line','partner_id','pricelist_id')
    def _compute_weaving_warning(self):
        for order in self:
            order.weaving_warning = ''
            if order.partner_id and not order.pricelist_id:
                order.weaving_warning += _(('This sale order has no price list or the option is not activated.')) + '\n'
            else:
                for line in order.order_line:
                    if line.product_template_id.bom_ids:
                        bom_id = line.product_template_id.bom_ids[0]
                        for bom_line in bom_id.bom_line_ids:
                            pricelist_item_id = line.order_id.pricelist_id._get_product_rule(
                                bom_line.product_id.product_tmpl_id,
                                quantity=bom_line.product_qty or 1.0,
                                uom=bom_line.product_uom_id,
                                date=line._get_order_date(),
                            )
                            if not pricelist_item_id and order.partner_id:
                                order.weaving_warning += _(('Product %s has product %s on its bom and does not have a price in %s price list. The price is obtained from its own sale price.') %( line.product_id.product_tmpl_id.name, bom_line.product_id.product_tmpl_id.name, order.pricelist_id.name)) + '\n'
                        for operation in bom_id.operation_ids:
                            if operation.operation_id.type_prices == 'col':
                                operation_color_line = operation.operation_id.product_color_price_ids.search([('product_color_id','=',line.product_color_id.id),('mrwo_id','=', operation.operation_id.id)])
                                if not operation_color_line:
                                    order.weaving_warning += (_('The type prices of %s operation is by color. The color %s does not exists in the operation color list of product %s.') %(operation.operation_id.name, line.product_color_id.name, line.product_id.product_tmpl_id.name)) + '\n'

    def action_price_preview(self):
        self.ensure_one()
        url = self.get_portal_url(suffix='/price_items')  # solo un suffix
        return {
            'type': 'ir.actions.act_url',
            'target': 'self',
            'url': url,
        }