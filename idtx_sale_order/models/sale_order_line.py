from odoo import models, fields, api, _, Command
from odoo.tools import float_round
from odoo.exceptions import UserError
import json

class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    product_color_id = fields.Many2one('product.color', string='Color')
    color_name = fields.Char('Color Name')
    # weaving_warning = fields.Text('weaving_warning')
    weaving_loss = fields.Float('Weaving Loss')
    production_loss = fields.Float('Production Loss')
    is_weaving = fields.Boolean(related='product_template_id.is_weaving', store=True)
    analysis_id = fields.Many2one(related='product_template_id.analysis_id')
    bom_id = fields.Many2one('mrp.bom', string='Bom')
    operation_ids = fields.Many2many('mrp.routing.workcenter', string='Operations')
    # lab_dev_ids = fields.Many2many(related='order_id.lab_dev_ids', store=True)
    available_operation_ids = fields.Many2many(
        'mrp.routing.workcenter',
        compute='_compute_available_operations',
        string='Available Operations'
    )
    # Campo para guardar los precios
    price_items = fields.Text(string='Price Items', default='{}')
    production_id = fields.Many2one('mrp.production', string='Production')
    parent_is_quote = fields.Boolean(related='order_id.is_quote')
    has_approved_lab_line = fields.Boolean(
        string='Approved',
        compute='_compute_has_approved_lab_line',
        store=False,
    )
    lab_dev_line_id = fields.Many2one('lab.dev.line', string='Lab Dev Line')
    diff_days = fields.Float('diff_days')
    
    def _compute_has_approved_lab_line(self):
        for line in self:
            line.has_approved_lab_line = bool(len(line.lab_dev_line_id.filtered(lambda l: l.state == 'approved')))

    @api.depends('bom_id')
    def _compute_available_operations(self):
        for record in self:
            operations = self.env['mrp.routing.workcenter'].search([])
            if record.bom_id:
                operations = record.bom_id.operation_ids.ids
            record.available_operation_ids = operations
    
    @api.onchange('bom_id')
    def _onchange_bom_id(self):
        for rec in self:
            rec.operation_ids = [Command.clear()]
            rec.operation_ids = rec.bom_id.operation_ids.sorted(key=lambda r: r.sequence)
            rec.weaving_loss = rec.bom_id.technical_sheet_id.scrap
            rec.production_id.bom_id = rec.bom_id

    def js_compute_price_unit(self):
        self._compute_price_unit()

    @api.onchange('product_id','product_color_id','operation_ids')
    def _onchange_product_or_color(self):
        self.price_items = '{}'
        self._compute_price_unit()

    @api.onchange('lab_dev_line_id')
    def _onchange_lab_dev_line_id(self):
        self._compute_has_approved_lab_line()

    @api.depends('product_id', 'product_template_id', 'product_uom_id', 'product_uom_qty','product_color_id', 'weaving_loss', 'production_loss','bom_id','operation_ids','order_id.payment_term_id','order_id.incoterm')
    def _compute_price_unit(self):
        res = super()._compute_price_unit()
        #Solo calcula el precio si la compañía produce
        if self.company_id.is_company_produce and self.product_id.is_weaving:
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
        # Si es una cotización hacemos los calculos
        if self.order_id.is_quote:
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
                # self.weaving_warning = ''
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
                    price = bom_line_price
                    if bom_line.operation_id.id in self.operation_ids._origin.ids:
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

        # Si no es una cotización entonces tomamos los precios desde la cotización siempre
        # que este asociada, de lo contrario los precios serán ingresados a mano.
        # TODO posible candado para no permitir hacer ordenes libres y no permitir cambiar precios
        else:
            # if self.order_id.quotation_id:
            line = self.get_product_from_quote(self.product_id, self.product_color_id)
            total = line.price_unit
            # else:
            #     total = 1
    
        return float_round(total, 2)
    
    def get_product_from_quote(self, product, color):
        if product and color:
            quote = self.order_id.quotation_id
            line = quote.order_line.filtered(lambda l: l.product_id == product and l.product_color_id == color)
            if not line:
                today = fields.Date.context_today(self)
                line = self._get_last_quotation_price(today)
                if line:
                    if line.order_id.validity_date <= today:
                        self.diff_days = (today - line.order_id.validity_date ).days
                    return line
                else:
                    raise UserError(_('Product %s with color %s can\'t be found in any quotation') %(product.name, color.name))
            return line
        else:
            return self.env['sale.order.line']
        
    def _get_last_quotation_price(self, today):
        lines = self.env['sale.order.line'].search([
            ('order_id.partner_id', '=', self.order_partner_id.id),
            ('product_id', '=', self.product_id.id),
            ('product_color_id', '=', self.product_color_id.id),
            ('order_id.is_quote', '=', True),
            ('order_id.state', 'in', ('draft','sent')),
        ])
        # ordenamos en Python por validez (más reciente primero)
        lines = lines - self
        if lines:
            line = max(lines, key=lambda l: l.order_id.validity_date or today.min)
        else:
            line = False
        return line