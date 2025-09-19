from odoo import models, fields, api, _, Command
from odoo.tools import float_round
from odoo.exceptions import UserError
import json

class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    product_color_id = fields.Many2one('product.color', string='Color')
    weaving_warning = fields.Text('weaving_warning')
    weaving_loss = fields.Float('Weaving Loss')
    production_loss = fields.Float('Production Loss')
    is_weaving = fields.Boolean(related='product_template_id.is_weaving', store=True)
    analysis_id = fields.Many2one(related='product_template_id.analysis_id')
    bom_id = fields.Many2one('mrp.bom', string='Bom')
    operation_ids = fields.Many2many('mrp.routing.workcenter', string='Operations')
    lab_dev_id = fields.Many2one(related='order_id.lab_dev_id')
    available_operation_ids = fields.Many2many(
        'mrp.routing.workcenter',
        compute='_compute_available_operations',
        string='Available Operations'
    )
    # Campo para guardar los precios
    price_items = fields.Text(string='Price Items', default='{}')

    @api.depends('bom_id')
    def _compute_available_operations(self):
        for record in self:
            products = self.env['mrp.routing.workcenter'].search([])
            if record.bom_id:
                products = record.bom_id.operation_ids.ids
            record.available_operation_ids = products
    
    @api.onchange('bom_id')
    def _onchange_bom_id(self):
        for rec in self:
            rec.operation_ids = [Command.clear()]
            rec.operation_ids = rec.bom_id.operation_ids.sorted(key=lambda r: r.sequence)
            rec.weaving_loss = rec.bom_id.technical_sheet_id.scrap

    def js_compute_price_unit(self):
        self._compute_price_unit()

    @api.onchange('product_id','product_color_id','operation_ids')
    def _onchange_product_or_color(self):
        self.price_items = '{}'

    @api.depends('product_id', 'product_template_id', 'product_uom_id', 'product_uom_qty','product_color_id', 'weaving_loss', 'production_loss','bom_id','operation_ids','order_id.payment_term_id','order_id.incoterm')
    def _compute_price_unit(self):
        res = super()._compute_price_unit()
        # Diferenciar si es un producto tejido para calcular su precio
        for line in self.filtered(lambda l: l.is_weaving):
            if not line.product_template_id.bom_ids:
                raise UserError(_('This product does not have any bom. Please check with product development.'))
            else:
                line.bom_id = line.product_template_id.bom_ids[0]
                line.price_unit = line.get_weaving_price_unit()
                line.technical_price_unit = line.price_unit
        return res
    
    def get_weaving_price_unit(self):
        self.ensure_one()
        try:
            price_dict = json.loads(self.price_items or '{}')
        except (json.JSONDecodeError, TypeError):
            price_dict = {}
        # Precio de Insumos
        if not self.bom_id:
            bom_id = self.product_template_id.bom_ids[0]
        else:
            bom_id = self.bom_id
        if not price_dict:
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
                price_dict.update({bom_line.product_id.name : price})
            # Precio de Operaciones
            for operation in self.operation_ids.sorted(key=lambda r: r.sequence):
                if operation.operation_id.type_prices == 'col':
                    operation_color_line = operation.operation_id.product_color_price_ids.search([('product_color_id','=',self.product_color_id.id),('mrwo_id','=', operation.operation_id._origin.id)])
                    if operation_color_line:
                        price = operation_color_line.unit_price
                else:
                    price = operation.operation_id.unit_price
                # Convertimos si es en otra moneda
                src_currency = operation.operation_id.currency_id
                if src_currency != currency:
                    price = src_currency._convert(price, currency, self.env.company, fields.Date.context_today(self), round=False)
                price_dict.update({operation.operation_id.name : price})
        
        # 1. Eliminar cualquier registro previo de merma de producción
        for key in list(price_dict.keys()):
            if key.startswith(_('Production Loss:')):
                price_dict.pop(key, None)
            if key.startswith(_('Financial Percentage:')):
                price_dict.pop(key, None)
            if key.startswith(_('Incoterm:')):
                price_dict.pop(key, None)

        # Suma total de insumos y procesos
        total = float_round(sum(price_dict.values()), 2) if price_dict else 0

        # ---- Merma de producción (se sincroniza siempre) ----
        scrap = self.weaving_loss or bom_id.technical_sheet_id.scrap
        production_loss_key = _('Production Loss: %.2f %%' % float_round(scrap * 100, 2))
        # Volver a añadir si corresponde
        if scrap:
            price = float_round(total * scrap, 2)
            total = float_round(total / (1 - scrap), 2)
            price_dict.update({production_loss_key: price})
        
        # ---- Terminos de pago (se sincroniza siempre) ----
        financial_key = _('Financial Percentage: %.2f %%') % (self.order_id.payment_term_id.financial_percentage * 100)
        # Volver a añadir si corresponde
        if self.order_id.payment_term_id and self.order_id.payment_term_id.financial_percentage:
            price = float_round(total * self.order_id.payment_term_id.financial_percentage, 2)
            total += float_round(total * (1 + self.order_id.payment_term_id.financial_percentage), 2)
            price_dict.update({financial_key: price})

        # ---- Incoterm (se sincroniza siempre) ----
        incoterm_key = _('Incoterm: ') + (self.order_id.incoterm.code if self.order_id.incoterm else '')
        # Volver a añadir si corresponde
        if self.order_id.incoterm and self.order_id.incoterm.unit_price:
            # total += self.order_id.incoterm.unit_price
            price_dict.update({incoterm_key: self.order_id.incoterm.unit_price})

        # Suma total de otra vez para verificar si se agregaron o se quitaron registros al sincronizar
        total = float_round(sum(price_dict.values()), 2) if price_dict else 0

        # Guarda la información de los precios en el campo
        self.price_items = json.dumps(price_dict)

        return float_round(total, 2)