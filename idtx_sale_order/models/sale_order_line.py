from odoo import models, fields, api, _, Command
from odoo.tools import float_round
from odoo.exceptions import UserError
import json

class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    product_color_id = fields.Many2one('product.color', string='Color')
    is_lab_color = fields.Boolean(related='product_color_id.is_lab_color')
    color_name = fields.Char('Color Name')
    # weaving_warning = fields.Text('weaving_warning')
    weaving_loss = fields.Float('Weaving Loss')
    production_loss = fields.Float('Production Loss')
    is_weaving = fields.Boolean(related='product_template_id.is_weaving', store=True)
    # Otra tecnica para saber si lleva estampado
    is_printing = fields.Boolean('is_printing', compute='_compute_is_printing', store=True, default=False)
    printing_design_id = fields.Many2one('printing.design', string='Design')
    printing_design_name = fields.Char(related='printing_design_id.file_desc')
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
    is_salesman = fields.Boolean('is_salesman?', compute='_compute_is_salesman')
    # Detalle de producto en cotización ingresado por comercial y Alex
    min_qty = fields.Float('Minimum Qty', default=1000.00)
    # Lo comentamos y usamos el campo customer_lead del estandar
    # lead_time = fields.Integer('Lead Time', default=30)
    dis_app = fields.Boolean('dis_app?', default=True)
    # Manejo de tallas para rectilineos
    is_rect = fields.Boolean(related='product_id.product_tmpl_id.is_rect')
    size_qty_ids = fields.One2many('sale.order.line.size', 'line_id', string='Size / Qty')
    has_weaving_operation = fields.Boolean(compute="_compute_has_weaving_operation", store=True)

    @api.depends('operation_ids')
    def _compute_has_weaving_operation(self):
        for line in self:
            line.has_weaving_operation = any(op.operation_id.operation_type == "weaving" for op in line.operation_ids)
    
    @api.onchange('printing_design_id')
    def _onchange_printing_design_id(self):
        for rec in self:
            if rec.bom_id and rec.bom_id.technical_sheet_id:
                yield_meter = rec.bom_id.technical_sheet_id.yield_meter
            else:
                yield_meter = rec.printing_design_id.yield_meter
            if rec.printing_design_id and rec.printing_design_id.printing_type == 'rotary':
                rec.min_qty = round(self.env.company.rotary_printing_min_qty / yield_meter)
            elif rec.printing_design_id and rec.printing_design_id.printing_type == 'digital':
                rec.min_qty = round(self.env.company.digital_printing_min_qty / yield_meter)
            else:
                rec.min_qty = 1000

    @api.onchange('discount')
    def _onchange_discount(self):
        max_discount = self.env.company.max_discount * 100
        if self.discount > max_discount:
            self.dis_app = False
        else:
            self.dis_app = True

    @api.depends_context("uid")
    def _compute_is_salesman(self):
        # Si pertenece a unos de estos 2 grupos no es vendedor entonces puede editar
        # Si solo puede ver sus propios documentos no edita precio
        is_admin = (self.env.user.has_group("sales_team.group_sale_salesman_all_leads") or self.env.user.has_group("sales_team.group_sale_manager"))
        for line in self:
            line.is_salesman = not is_admin
            
    @api.depends('lab_dev_line_id')
    def _compute_has_approved_lab_line(self):
        for line in self:
            line.has_approved_lab_line = bool(len(line.lab_dev_line_id.filtered(lambda l: l.state == 'approved')))

    @api.depends('bom_id')
    def _compute_available_operations(self):
        for record in self:
            operations = self.env['mrp.routing.workcenter']
            if record.bom_id:
                operations = record.bom_id.operation_ids.filtered(lambda o: o.operation_id.unit_price > 0 or o.operation_id.type_prices == 'col' and sum(o.operation_id.product_color_price_ids.mapped('unit_price')) > 0 or o.operation_id.operation_type == 'weaving').ids
            record.available_operation_ids = operations
    
    @api.depends('bom_id')
    def _compute_is_printing(self):
        for rec in self:
            rec.is_printing = bool(any(p.operation_type == 'printing' for p in rec.bom_id.operation_ids.mapped('operation_id')))

    @api.onchange('bom_id','product_color_id')
    def _onchange_bom_id(self):
        for rec in self:
            rec.operation_ids = [Command.clear()]
            rec.operation_ids = rec.bom_id.operation_ids.filtered(lambda o: o.operation_id.unit_price > 0 or o.operation_id.type_prices == 'col' and sum(o.operation_id.product_color_price_ids.mapped('unit_price')) > 0 or o.operation_id.operation_type == 'weaving').sorted(key=lambda r: r.sequence)
            rec.weaving_loss = rec.bom_id.technical_sheet_id.scrap
            rec.production_loss = rec.bom_id.technical_sheet_id.prod_scrap
            rec.production_id.bom_id = rec.bom_id

    def js_compute_price_unit(self):
        self._compute_price_unit()

    @api.onchange('product_id','product_color_id','operation_ids','printing_design_id')
    def _onchange_product_or_color(self):
        for rec in self:
            if rec.parent_is_quote and rec.product_color_id:
                # Validar que no exista otra línea con el mismo color en esta cotización
                existing_lines = rec.order_id.order_line.filtered(
                    lambda l: l.product_color_id == rec.product_color_id and l.product_id == rec.product_id
                ) - rec
                if existing_lines:
                    # Si es printing, permitir si el diseño es diferente
                    if rec.is_printing:
                        same_design_lines = existing_lines.filtered(
                            lambda l: l.printing_design_id == rec.printing_design_id and l.is_printing
                        )
                        if same_design_lines:
                            raise UserError(_('Cannot quote the same color with the same design twice.'))
                    else:
                        raise UserError(_('Cannot quote the same color twice.'))
            rec.price_items = '{}'
        # self._compute_price_unit()

    @api.onchange('lab_dev_line_id')
    def _onchange_lab_dev_line_id(self):
        for rec in self:
            rec._compute_has_approved_lab_line()
            if rec.lab_dev_line_id and not rec.color_name:
                rec.color_name = rec.lab_dev_line_id.color_name

    @api.onchange('product_id')
    def _onchange_product_id(self):
        res = super()._onchange_product_id()
        if self.is_weaving and self.product_template_id.bom_ids:
            self.bom_id = self.product_template_id.bom_ids[0]
        return res

    @api.depends('product_id',
                 'product_template_id',
                 'product_uom_id',
                 'product_uom_qty',
                 'product_color_id',
                 'weaving_loss',
                 'production_loss',
                 'bom_id',
                 'operation_ids',
                 'order_id.payment_term_id',
                 'order_id.incoterm',
                 'printing_design_id',
                 'min_qty',
                 'order_id.sale_type')
    def _compute_price_unit(self):
        res = super()._compute_price_unit()
        #Solo calcula el precio si la compañía produce
        for line in self.filtered(lambda l: l.is_weaving):
            if line.company_id.is_company_produce and line.product_id.is_weaving:
                # Diferenciar si es un producto tejido para calcular su precio
                # for line in self.filtered(lambda l: l.is_weaving):
                if line.product_template_id.bom_ids:
                    # line.bom_id = line.product_template_id.bom_ids[0]
                    line.price_unit = line.get_weaving_price_unit()
                    line.technical_price_unit = line.price_unit
        return res
    
    # ---------- MÉTODO CORREGIDO (CLAVES FIJAS + LABEL TRADUCIBLE) ----------
    def get_weaving_price_unit(self):
        """
        Calcula el precio unitario para productos de tejido.
        """
        self.ensure_one()
        if self.order_id.is_quote:
            try:
                price_dict = json.loads(self.price_items or '{}')
            except (json.JSONDecodeError, TypeError):
                price_dict = {}

            # 1) CLAVES FIJAS (sin _() → nunca se traducen)
            WEAV_LOSS_KEY = "Weaving Loss"
            PROD_LOSS_KEY = "Production Loss"
            FINANCIAL_KEY = "Financial Percentage"
            INCOTERM_KEY  = "Incoterm"

            # 2) Elimina previos por clave FIJA (sin traducción)
            for key in list(price_dict.keys()):
                if key in (WEAV_LOSS_KEY, PROD_LOSS_KEY, FINANCIAL_KEY, INCOTERM_KEY):
                    price_dict.pop(key, None)

            # 3) Calcula insumos y operaciones (tu lógica sin cambios)
            # ------------------------------------------------------------------
            currency = self.order_id.pricelist_id.currency_id
            bom_id = self.bom_id or self.product_template_id.bom_ids[0]
            weaving = self.has_weaving_operation #any(operation.operation_id.operation_type == 'weaving' for operation in self.operation_ids)
            thread_total = 0

            if not price_dict:
                if weaving and self.order_id.sale_type == 'sale':
                    for bom_line in bom_id.bom_line_ids.filtered(lambda l: l.product_tmpl_id.categ_id in self.env.company.thread_category_ids):
                        pricelist_item_id = self.order_id.pricelist_id._get_product_rule(
                            bom_line.product_id,
                            quantity=bom_line.product_qty or 1.0,
                            uom=bom_line.product_uom_id,
                            date=self._get_order_date(),
                        )
                        if pricelist_item_id:
                            bom_line_price = self.env['product.pricelist.item'].browse(pricelist_item_id)._compute_price(
                                product=bom_line.product_id,
                                quantity=bom_line.product_qty or 1.0,
                                uom=bom_line.product_uom_id,
                                date=self._get_order_date(),
                                currency=self.currency_id,
                            )
                        else:
                            bom_line_price = self.env.company.currency_id._convert(
                                bom_line.product_id.list_price,
                                currency,
                                self.env.company,
                                fields.Date.context_today(self),
                                round=False
                            )
                        # if 'DUPONT' in bom_line.product_id.name.upper():
                        #     qty = 1
                        # else:
                        qty = bom_line.product_qty 
                        price = float_round(bom_line_price * qty, 2)
                        product_name = bom_line.product_id.name
                        price_dict.setdefault(product_name, {'label': product_name, 'price': 0.0})
                        price_dict[product_name]['price'] += float_round(bom_line_price * qty, 2)

                    for v in price_dict.values():
                        v['is_thread'] = True

                # elif not price_dict:
                #     thread_total = float_round(sum([v['price'] for v in price_dict.values() if v.get('is_thread')]), 2) if price_dict else 0

                for operation in self.operation_ids.sorted(key=lambda r: r.sequence):
                    if operation.operation_id.operation_type == 'weaving':
                        price = float_round(self.product_template_id.analysis_id.weaving_price,2)
                    else:
                        if operation.operation_id.type_prices == 'col':
                            operation_color_line = operation.operation_id.product_color_price_ids.search([
                                ('product_color_id', '=', self.product_color_id.id),
                                ('mrwo_id', '=', operation.operation_id._origin.id)
                            ])
                            # Si el precio varia por titulo de hilo
                            if operation.operation_id.per_title:
                                operation_color_title_line = operation_color_line.color_title_price_ids.filtered(lambda l: self.product_template_id.analysis_id.product_title_id in l.title_ids)
                                price = float_round(operation_color_title_line.unit_price, 2) if operation_color_title_line else 0
                            else:
                                price = float_round(operation_color_line.unit_price, 2) if operation_color_line else 0
                        else:
                            price = float_round(operation.operation_id.unit_price, 2)
                    
                    # Si el precio varia por titulo de hilo
                    # if operation.operation_id.per_title:
                    #     if operation.operation_id.type_prices == 'col':
                    #         if self.product_color_id.is_lab_color:
                    #             price = float_round(price + self.product_template_id.analysis_id.product_title_id.unit_price, 2)
                    #     else:
                    #         price = float_round(price + self.product_template_id.analysis_id.product_title_id.unit_price, 2)

                    src_currency = operation.operation_id.currency_id
                    if src_currency != currency:
                        price = src_currency._convert(
                            price,
                            currency,
                            self.env.company,
                            fields.Date.context_today(self),
                            round=False
                        )
                    if price:
                    # price_dict.update({operation.operation_id.name: price})
                        price_dict.update({operation.operation_id.name: {'label': operation.operation_id.name, 'price': price}})

            # Agregamos precio de estampado si existiera# Agregamos precio de estampado si existiera
            if self.printing_design_id:
                printing = price_dict.get('PRINTING')
                if not printing or printing.get('design_id') != self.printing_design_id.id or printing.get('qty') != self.product_uom_qty or printing.get('min_qty') != self.min_qty:
                    price_dict.pop('PRINTING', None)
                    yield_meter = float_round(self.bom_id.technical_sheet_id.yield_meter if self.bom_id.technical_sheet_id else self.printing_design_id.yield_meter, 2)
                    if self.order_id.is_quote:
                        total_qty = round(self.min_qty * yield_meter)
                    else:
                        total_qty = round(self.product_uom_qty * yield_meter)
                    price = 0
                    if self.printing_design_id.printing_type == 'digital':
                        if total_qty > 59.99:
                            for line in self.printing_design_id.digital_unit_price_ids:
                                if total_qty >= line.min_qty and total_qty <= line.max_qty:
                                    price = float_round(line.unit_price * yield_meter, 2)
                        else:
                            price = self.printing_design_id.digital_unit_price_ids[0].unit_price
                    else:
                        price = float_round(self.printing_design_id.unit_price * yield_meter, 2)
                    price_dict['PRINTING'] = {
                        'label': _('PRINTING'),
                        'price': price,
                        'design_id': self.printing_design_id.id,
                        'min_qty': self.min_qty,
                        'qty': self.product_uom_qty,
                    }
            else:
                price_dict.pop('PRINTING', None)

            # 4) Totales y derivados con clave FIJA + label traducible
            # ------------------------------------------------------------------
            total = float_round(sum([v["price"] for v in price_dict.values()]), 2) if price_dict else 0

            if weaving:
                thread_total = float_round(sum([v['price'] for v in price_dict.values() if v.get('is_thread')]), 2) if price_dict else 0
                scrap = self.weaving_loss or bom_id.technical_sheet_id.scrap
                if scrap:
                    loss = float_round(thread_total * scrap, 2)
                    total = float_round(total + loss, 2)
                    price_dict[WEAV_LOSS_KEY] = {
                        "price": loss,
                        "label": _("Weaving Loss:") + " %.2f %%" % (scrap * 100)
                    }
            
            prod_scrap = self.production_loss or bom_id.technical_sheet_id.prod_scrap

            if prod_scrap:
                loss = float_round(total * prod_scrap, 2)
                total = float_round(total / (1 - prod_scrap), 2)
                price_dict[PROD_LOSS_KEY] = {
                    "price": loss,
                    "label": _("Production Loss:") + " %.2f %%" % (prod_scrap * 100)
                }

            if self.order_id.payment_term_id and self.order_id.payment_term_id.financial_percentage:
                financial = float_round(total * self.order_id.payment_term_id.financial_percentage, 2)
                total += financial
                price_dict[FINANCIAL_KEY] = {
                    "price": financial,
                    "label": _("Financial Percentage:") + " %.2f %%" % (self.order_id.payment_term_id.financial_percentage * 100)
                }

            if self.order_id.incoterm and self.order_id.incoterm.unit_price:
                price_dict[INCOTERM_KEY] = {
                    "price": self.order_id.incoterm.unit_price,
                    "label": _("Incoterm:") + " %s" % (self.order_id.incoterm.code or '')
                }

            # 5) Guarda JSON con estructura {key: {"price": float, "label": str}}
            total = float_round(sum([v["price"] for v in price_dict.values()]), 2) if price_dict else 0
            self.price_items = json.dumps(price_dict)

        # Si NO es cotización → tu lógica anterior (sin cambios)
        else:
            line = self.get_product_from_quote(self.product_id, self.product_color_id, self.bom_id, self.printing_design_id)
            total = line.price_unit if line else 1

        return float_round(total, 2)
    
    def get_product_from_quote(self, product, color, bom, printing_design_id):
        if product and color:
            quote = self.order_id.quotation_id
            line = quote.order_line.filtered(lambda l: l.product_id == product and l.product_color_id == color and l.bom_id == bom and l.printing_design_id == printing_design_id)
            if not line:
                today = fields.Date.context_today(self)
                line = self._get_last_quotation_price(today)
                if line:
                    if line.order_id.validity_date <= today:
                        self.diff_days = (today - line.order_id.validity_date ).days
                    return line
                else:
                    raise UserError(_('Product %s with color %s can\'t be found in any quotation or sale order. Please quotate first.') %(product.name, color.name))
            return line
        else:
            return self.env['sale.order.line']
        
    def _get_last_quotation_price(self, today):
        lines = self.env['sale.order.line'].search([
            ('order_id.partner_id', '=', self.order_partner_id.id),
            ('product_id', '=', self.product_id.id),
            ('product_color_id', '=', self.product_color_id.id),
            ('printing_design_id', '=', self.printing_design_id.id),
            # ('order_id.is_quote', '=', True),
            ('operation_ids','=', self.operation_ids.ids),
            ('order_id.state', 'in', ('draft','sent')),
        ])
        # ordenamos en Python por validez (más reciente primero)
        lines = lines - self
        if lines:
            line = max(lines, key=lambda l: l.order_id.validity_date or today.min)
        else:
            line = False
        return line
    
    def write(self, vals):
        for rec in self:
            if 'product_uom_qty' in vals:
                rec.production_id.product_qty = vals.get('product_uom_qty')
        return super().write(vals)
    
    def action_open_size_qty_wizard(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "Size Qty (Rectilinear)",
            "res_model": "size.qty.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "active_model": self._name,
                "active_id": self.id,
            },
        }
    
class SaleOrderLineSize(models.Model):
    _name = 'sale.order.line.size'
    _description = 'Sale Order Line Size'

    line_id = fields.Many2one('sale.order.line', string='Sale Order Line', required=True, ondelete="cascade")
    sequence = fields.Integer(default=10)
    size = fields.Char(string='Size')
    product_qty = fields.Integer('Product Qty', required=True, default=0)
    # length = fields.Float(string="Largo (cm)")
    # width = fields.Float(string="Ancho (cm)")