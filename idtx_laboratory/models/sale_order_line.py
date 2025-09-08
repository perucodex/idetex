from odoo import models, fields, api, _
from odoo.tools import float_round
from odoo.exceptions import UserError

class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    product_color_id = fields.Many2one('product.color', string='Color')
    weaving_warning = fields.Text('weaving_warning')
    weaving_loss = fields.Float('Weaving Loss')
    production_loss = fields.Float('Production Loss')
    is_weaving = fields.Boolean(related='product_template_id.is_weaving', store=True)
    analysis_id = fields.Many2one('product_template_id.analysis_id')
    bom_id = fields.Many2one('mrp.bom', string='Bom')
    operation_ids = fields.Many2many('mrp.routing.workcenter.operation', string='Operations')
    # technical_sheet_id = fields.Many2one(related='bom_id.technical_sheet_id', store=True)
    # is_size = fields.Boolean('Is size?', compute='_compute_is_size', store=True)
    # size_ids = fields.Many2many('technical.size.line', string='Size')
    # labdev_color_name = fields.Char('Lab Dev Color Name')
    # labdev_color_id = fields.Many2one('lab.dev.line', string='Lab Dev Color ID')
    lab_dev_id = fields.Many2one(related='order_id.lab_dev_id')
    available_operation_ids = fields.Many2many(
        'mrp.routing.workcenter.operation',
        compute='_compute_available_operations',
        string='Available Operations'
    )

    @api.depends('bom_id')
    def _compute_available_operations(self):
        for record in self:
            products = self.env['mrp.routing.workcenter.operation'].search([])
            if record.bom_id:
                products = record.bom_id.operation_ids.mapped('operation_id').ids
            record.available_operation_ids = products
    
    @api.onchange('bom_id')
    def _onchange_bom_id(self):
        for rec in self:
            rec.operation_ids = rec.bom_id.operation_ids.mapped('operation_id').ids

    # @api.onchange('labdev_color_id')
    # def _onchange_labdev_color_id(self):
    #     self.labdev_color_name = self.labdev_color_id.color_name

    # @api.depends('product_id','product_template_id')
    # def _compute_is_size(self):
    #     for rec in self:
    #         rec.is_size = True if rec.technical_sheet_id.weave_type == 'rect' else False

    @api.depends('product_id','product_template_id')
    def _compute_is_size(self):
        for rec in self:
            if not rec.product_template_id.bom_ids and rec.product_template_id.is_weaving:
                raise UserError(_('This product does not have any bom. Please check with product development.'))
            else:
                rec.bom_id = rec.product_template_id.bom_ids[0]

    @api.depends('product_id', 'product_template_id', 'product_uom', 'product_uom_qty','product_color_id', 'weaving_loss', 'production_loss','bom_id','operation_ids')
    def _compute_price_unit(self):
        res = super()._compute_price_unit()
        # Diferenciar si es un producto tejido para calcular su precio
        for line in self.filtered(lambda l: l.is_weaving):
            if line.product_template_id.bom_ids:
                line.price_unit = line._get_weaving_price_unit()
                line.technical_price_unit = line.price_unit
        return res
    
    def _get_weaving_price_unit(self):
        self.ensure_one()
        price_list = []
        # Precio de Insumos
        if not self.bom_id:
            bom_id = self.product_template_id.bom_ids[0]
        else:
            bom_id = self.bom_id
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
        for operation in self.operation_ids:
            if operation.type_prices == 'col':
                operation_color_line = operation.product_color_price_ids.search([('product_color_id','=',self.product_color_id.id),('mrwo_id','=', operation._origin.   id)])
                if operation_color_line:
                    price = operation_color_line.unit_price
            else:
                price = operation.unit_price
            # Convertimos si es en otra moneda
            src_currency = operation.currency_id
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