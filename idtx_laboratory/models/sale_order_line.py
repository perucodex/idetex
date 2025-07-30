from odoo import models, fields, api, _
from odoo.exceptions import UserError
from odoo.tools import float_round

class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    product_color_id = fields.Many2one('product.color', string='Color')
    weaving_warning = fields.Text('weaving_warning')
    weaving_loss = fields.Float('Weaving Loss')
    production_loss = fields.Float('Production Loss')
    is_weaving = fields.Boolean(related='product_template_id.is_weaving', store=True)

    @api.depends('product_id', 'product_uom', 'product_uom_qty','product_color_id', 'weaving_loss', 'production_loss')
    def _compute_price_unit(self):
        res = super()._compute_price_unit()
        for line in self:
            # Diferenciar si es un producto tejido para calcular su precio
            if line.product_template_id.bom_ids:
                line.price_unit = line._get_weaving_price_unit()
                line.technical_price_unit = line.price_unit
        return res
    
    def _get_weaving_price_unit(self):
        self.ensure_one()
        price_list = []
        # Precio de Insumos
        bom_id = self.product_template_id.bom_ids[0]
        currency = self.order_id.pricelist_id.currency_id
        self.weaving_warning = ''
        for bom_line in bom_id.bom_line_ids.filtered(lambda l: l.product_tmpl_id.categ_id in self.env.company.thread_category_ids):
            pricelist_item_id = self.order_id.pricelist_id._get_product_rule(
                bom_line.product_id,
                quantity=bom_line.product_qty or 1.0,
                uom=bom_line.product_uom_id,
                date=self._get_order_date(),
            )
            if pricelist_item_id:
                bom_line_price = self.env['product.pricelist.item'].search([('id','=', pricelist_item_id)])._compute_price(
                    product=bom_line.product_id.with_context(**{}),
                    quantity=bom_line.product_qty or 1.0,
                    uom=bom_line.product_uom_id,
                    date=self._get_order_date(),
                    currency=self.currency_id,
                )
            else:
                bom_line_price = self.env.company.currency_id._convert(bom_line.product_id.list_price, currency, self.env.company, fields.Date.context_today(self), round=False)
            # Si es hilado obtener el factor de cada hilado desde la ficha tecnica del producto
            # if self.product_template_id.is_thread
            # factor = self.product_template_id.technical_sheet....
            factor = 1
            price = float_round(bom_line_price * factor / (1 - self.weaving_loss), 2)
            price_list.append(price)
        # Precio de Operaciones
        for operation in bom_id.operation_ids:
            if operation.operation_id.type_prices == 'col':
                operation_color_line = operation.operation_id.product_color_price_ids.search([('product_color_id','=',self.product_color_id.id),('mrwo_id','=', operation.operation_id.id)])
                if operation_color_line:
                    price = operation_color_line.unit_price
            else:
                price = operation.operation_id.unit_price
            # Convertimos si es en otra moneda
            src_currency = operation.operation_id.currency_id
            if src_currency != currency:
                price = src_currency._convert(price, currency, self.env.company, fields.Date.context_today(self), round=False)
            price_list.append(price)
        # Suma total de insumos y procesos
        total = float_round(sum(price_list), 2)
        # Aplicamos la merma de producción
        total = float_round(total / (1 - self.production_loss), 2)
        # Agregamos el porcentaje de financiamiento desde la forma de pago
        if self.order_id.payment_term_id.financial_percentage:
            total *= 1 + self.order_id.payment_term_id.financial_percentage
        # Agregamos el monto del incoterm
        if self.order_id.incoterm and self.order_id.incoterm.unit_price:
            total += self.order_id.incoterm.unit_price
        return float_round(total, 2)