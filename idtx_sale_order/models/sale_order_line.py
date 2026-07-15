from odoo import models, fields, api, _, Command
from odoo.tools import float_round
from odoo.exceptions import UserError
import json

META_KEY = "__price_meta__"
WEAV_LOSS_KEY = "Weaving Loss"
PROD_LOSS_KEY = "Production Loss"
FINANCIAL_KEY = "Financial Percentage"
INCOTERM_KEY = "Incoterm"

class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    product_color_id = fields.Many2one('product.color', string='Color')
    # Rangos/intensidades configurados en el color, para filtrar lab_dev_line_id.
    product_color_range_ids = fields.Many2many(
        'color.range', related='product_color_id.color_range_ids',
        string='Color Ranges (from color)')
    product_color_intensity_ids = fields.Many2many(
        'color.intensity', related='product_color_id.color_intensity_ids',
        string='Color Intensities (from color)')
    is_lab_color = fields.Boolean(compute='_compute_is_lab_color', store=True)
    color_name = fields.Char('Color Name')
    # weaving_warning = fields.Text('weaving_warning')
    weaving_loss = fields.Float('Weaving Loss')
    production_loss = fields.Float('Production Loss')
    is_weaving = fields.Boolean(related='product_template_id.is_weaving', store=True)
    # Otra tecnica para saber si lleva estampado
    is_printing = fields.Boolean('is_printing', compute='_compute_is_printing', store=True, default=False)
    printing_design_id = fields.Many2one('printing.design', string='Design')
    printing_design_name = fields.Char(related='printing_design_id.file_desc')
    printing_design_preview_image = fields.Binary(related='printing_design_id.preview_image', readonly=True)
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
    production_id = fields.Many2one('mrp.production', string='Production', copy=False)
    parent_is_quote = fields.Boolean(related='order_id.is_quote')
    parent_is_company_produce = fields.Boolean(related='order_id.is_company_produce')
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
    # Línea marcada como "complemento" (solo cotizaciones). Se pinta en gris
    # como una sección y hereda el color de la línea anterior.
    is_complement = fields.Boolean(string='Es complemento', default=False, copy=True)

    @api.depends(
        'order_id.is_quote',
        'bom_id',
        'operation_ids',
        'operation_ids.operation_id',
        'operation_ids.operation_id.operation_type',
        'product_template_id',
        'product_template_id.analysis_id.routing_ids',
        'product_template_id.analysis_id.routing_ids.operation_id',
        'product_template_id.analysis_id.routing_ids.operation_id.operation_type',
    )
    def _compute_has_weaving_operation(self):
        for line in self:
            # Lectura con sudo: referencia operaciones/rutas de produccion que
            # el comercial puede no tener permiso de leer (grupo Fabricacion).
            sline = line.sudo()
            if not sline.bom_id:
                line.has_weaving_operation = any(
                    op.operation_type == "weaving"
                    for op in sline.product_template_id.analysis_id.routing_ids.mapped('operation_id')
                ) if sline.product_template_id else False
            elif sline.order_id.is_quote:
                line.has_weaving_operation = any(op.operation_id.operation_type == "weaving" for op in sline.operation_ids)
            else:
                line.has_weaving_operation = any(
                    op.operation_id.operation_type == "weaving"
                    for op in sline.bom_id.operation_ids
                )
    
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
            
    @api.depends('lab_dev_line_id', 'lab_dev_line_id.state',
                 'lab_dev_line_id.color_recipe_ids.state',
                 'lab_dev_line_id.color_recipe_ids.product_ids',
                 'product_template_id')
    def _compute_has_approved_lab_line(self):
        # El badge del color solo es verde si la línea de Lab Dev tiene una
        # receta APROBADA que incluya al PRODUCTO de esta línea de venta
        # (receta individual o de combinación de productos).
        for line in self:
            line.has_approved_lab_line = bool(line.lab_dev_line_id and any(
                cr.state == 'approved' and line.product_template_id in cr.product_ids
                for cr in line.lab_dev_line_id.color_recipe_ids))

    @api.depends(
        'bom_id',
        'bom_id.operation_ids',
        'bom_id.operation_ids.operation_id',
        'bom_id.operation_ids.operation_id.gives_color',
    )
    def _compute_is_lab_color(self):
        for line in self:
            sline = line.sudo()
            line.is_lab_color = any(op.operation_id.gives_color for op in sline.bom_id.operation_ids) if sline.bom_id else False

    @api.depends('bom_id')
    def _compute_available_operations(self):
        for record in self:
            srecord = record.sudo()
            operations = self.env['mrp.routing.workcenter']
            if srecord.bom_id:
                operations = srecord.bom_id.operation_ids.filtered(lambda o: o.operation_id.unit_price > 0 or o.operation_id.type_prices == 'col' and sum(o.operation_id.product_color_price_ids.mapped('unit_price')) > 0 or o.operation_id.type_prices == 'col' and o.operation_id.per_title and sum(o.operation_id.product_color_price_ids.color_title_price_ids.mapped('unit_price')) > 0 or o.operation_id.operation_type == 'weaving').ids
            record.available_operation_ids = operations
    
    @api.depends('bom_id')
    def _compute_is_printing(self):
        for rec in self:
            srec = rec.sudo()
            rec.is_printing = bool(any(p.operation_type == 'printing' for p in srec.bom_id.operation_ids.mapped('operation_id')))

    @api.onchange('bom_id','product_color_id')
    def _onchange_bom_id(self):
        for rec in self:
            # Lectura con sudo del BoM/operaciones (datos de produccion) para
            # que el comercial sin grupo de Fabricacion pueda seleccionar la
            # LdM y se calculen las operaciones con precio sin AccessError.
            srec = rec.sudo()
            rec.operation_ids = [Command.clear()]
            rec.operation_ids = srec.bom_id.operation_ids.filtered(lambda o: o.operation_id.unit_price > 0 or o.operation_id.type_prices == 'col' and sum(o.operation_id.product_color_price_ids.mapped('unit_price')) > 0 or o.operation_id.type_prices == 'col' and o.operation_id.per_title and sum(o.operation_id.product_color_price_ids.color_title_price_ids.mapped('unit_price')) > 0 or o.operation_id.operation_type == 'weaving').sorted(key=lambda r: r.sequence)
            rec.weaving_loss = srec.bom_id.technical_sheet_id.scrap or 0.01
            rec.production_loss = srec.bom_id.technical_sheet_id.prod_scrap or 0.09
            rec.production_id.bom_id = rec.bom_id

    def js_compute_price_unit(self):
        for line in self:
            try:
                price_dict = json.loads(line.price_items or '{}')
            except (json.JSONDecodeError, TypeError):
                price_dict = {}

            total = float_round(
                sum(
                    float(item.get('price', 0.0))
                    for key, item in (price_dict or {}).items()
                    if not str(key).startswith('__') and isinstance(item, dict)
                ),
                2,
            )
            line.price_unit = total
            line.technical_price_unit = total

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

    @api.onchange('is_complement')
    def _onchange_is_complement_color(self):
        """Al marcar la línea como complemento, hereda el product_color_id y
        el color_name de la línea anterior (la inmediatamente superior que sea
        un producto)."""
        for rec in self:
            if not rec.is_complement:
                continue
            order = rec.order_id
            if not order:
                continue
            # Recorremos en el orden natural del recordset (orden mostrado).
            # No reordenamos por `sequence`: la línea recién creada aún no
            # tiene un sequence mayor y quedaría mal posicionada.
            previous = None
            for line in order.order_line:
                if line == rec:
                    break
                if not line.display_type:
                    previous = line
            if not previous:
                raise UserError(_(
                    "No se puede agregar un complemento: no hay una línea de "
                    "producto anterior a la cual complementar."))
            # Herencia por comodidad: solo rellena vacíos. El complemento
            # puede elegir su propio color (color_name / lab_dev_line_id).
            if previous.product_color_id and not rec.product_color_id:
                rec.product_color_id = previous.product_color_id
            if previous.color_name and not rec.color_name:
                rec.color_name = previous.color_name

    @api.onchange('lab_dev_line_id')
    def _onchange_lab_dev_line_id(self):
        for rec in self:
            rec._compute_has_approved_lab_line()
            if rec.lab_dev_line_id and not rec.color_name:
                rec.color_name = rec.lab_dev_line_id.color_name
            # Actualiza las ordenes de producción relacionadas con esta línea de venta para que tengan el lab_dev_line_id asignado
            if rec.lab_dev_line_id and rec.lab_dev_line_id.state == 'approved' and rec.production_id:
                if any(wo.state == 'progress' for wo in rec.production_id.workorder_ids.filtered(lambda wo: wo.mrwo_id.use_lab_recipe)):
                    raise UserError(_('Cannot change recipe because there are workorders in progress using the lab recipe.'))
                rec.production_id.color_recipe_id = rec.lab_dev_line_id.color_recipe_ids.filtered(
                    lambda cr: cr.state == 'approved' and rec.production_id.product_tmpl_id in cr.product_ids)[:1]

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
                manual_dict = line._load_price_items_dict(line.price_items)

                if manual_dict.get('__manual_override__'):
                    order_pricelist = line.order_id.pricelist_id or line._get_pricing_pricelist()
                    currency = order_pricelist.currency_id or line.currency_id
                    conversion_date = line._get_order_date() or fields.Date.context_today(line)
                    adjusted_dict, total_manual = line._apply_order_price_adjustments(
                        manual_dict,
                        currency,
                        conversion_date,
                    )
                    line.price_items = json.dumps(adjusted_dict)
                    line.price_unit = total_manual
                    line.technical_price_unit = total_manual
                    continue

                # Diferenciar si es un producto tejido para calcular su precio
                # for line in self.filtered(lambda l: l.is_weaving):
                # if line.product_template_id.bom_ids:
                    # line.bom_id = line.product_template_id.bom_ids[0]
                line.price_unit = line.get_weaving_price_unit()
                line.technical_price_unit = line.price_unit
        return res

    def _convert_amount(self, amount, source_currency, target_currency, conversion_date=None):
        self.ensure_one()
        if not amount or not source_currency or not target_currency or source_currency == target_currency:
            return amount
        conversion_date = conversion_date or self._get_order_date() or fields.Date.context_today(self)
        return source_currency._convert(
            amount,
            target_currency,
            self.company_id,
            conversion_date,
            round=False,
        )

    def _get_pricing_pricelist(self):
        self.ensure_one()
        return self.order_id.company_id.sales_pricelist_id or self.order_id.pricelist_id

    def _load_price_items_dict(self, raw_value):
        self.ensure_one()
        try:
            price_dict = json.loads(raw_value or '{}')
        except (json.JSONDecodeError, TypeError, ValueError):
            price_dict = {}
        if isinstance(price_dict, dict):
            for key, value in price_dict.items():
                if str(key).startswith('__') or not isinstance(value, dict) or 'price' not in value:
                    continue
                try:
                    value['price'] = float_round(float(value.get('price', 0.0) or 0.0), 2)
                except (TypeError, ValueError):
                    value['price'] = 0.0
        return price_dict if isinstance(price_dict, dict) else {}

    def _sum_price_items(self, price_dict):
        self.ensure_one()
        return float_round(
            sum(
                float(item.get('price', 0.0))
                for key, item in (price_dict or {}).items()
                if not str(key).startswith('__') and isinstance(item, dict)
            ),
            2,
        )

    def _copy_price_items_to_currency(self, price_dict, source_currency, target_currency, conversion_date):
        self.ensure_one()
        converted_dict = {}
        for key, value in (price_dict or {}).items():
            if str(key).startswith('__'):
                if key != META_KEY:
                    converted_dict[key] = value
                continue

            if isinstance(value, dict):
                new_value = dict(value)
                amount = float(value.get('price', 0.0) or 0.0)
            else:
                new_value = {'label': key}
                amount = float(value or 0.0)

            new_value['price'] = float_round(
                self._convert_amount(amount, source_currency, target_currency, conversion_date),
                2,
            )
            new_value.setdefault('label', key)
            converted_dict[key] = new_value
        return converted_dict

    def _apply_order_price_adjustments(self, price_dict, currency, conversion_date):
        self.ensure_one()
        adjusted_dict = {}
        for key, value in (price_dict or {}).items():
            if key in (FINANCIAL_KEY, INCOTERM_KEY):
                continue
            adjusted_dict[key] = value

        total = self._sum_price_items(adjusted_dict)

        if self.order_id.payment_term_id and self.order_id.payment_term_id.financial_percentage:
            financial = float_round(total * self.order_id.payment_term_id.financial_percentage, 2)
            adjusted_dict[FINANCIAL_KEY] = {
                'price': financial,
                'label': _("Financial Percentage:") + " %.2f %%" % (self.order_id.payment_term_id.financial_percentage * 100),
            }
            total = float_round(total + financial, 2)

        if self.order_id.incoterm and self.order_id.incoterm.unit_price:
            incoterm_price = float_round(
                self._convert_amount(
                    self.order_id.incoterm.unit_price,
                    self.order_id.incoterm.currency_id,
                    currency,
                    conversion_date,
                ),
                2,
            )
            adjusted_dict[INCOTERM_KEY] = {
                'price': incoterm_price,
                'label': _("Incoterm:") + " %s" % (self.order_id.incoterm.code or ''),
            }
            total = float_round(total + incoterm_price, 2)

        return adjusted_dict, total
    
    # ---------- MÉTODO CORREGIDO (CLAVES FIJAS + LABEL TRADUCIBLE) ----------
    def get_weaving_price_unit(self):
        """
        Calcula el precio unitario para productos de tejido.

        El calculo referencia datos de produccion (BoM, operaciones, analisis,
        lista de precios, compania) que pueden pertenecer a otra compania
        (p. ej. fullpima) o requerir el grupo de Fabricacion. El comercial NO
        necesita acceso directo a esos modelos para cotizar: el computo corre
        en el servidor. Por eso leemos/computamos con sudo. La escritura de
        price_items/price_unit es sobre la propia linea (que el usuario posee).
        """
        self.ensure_one()
        self = self.sudo()
        if self.order_id.is_quote:
            price_dict = self._load_price_items_dict(self.price_items)

            # 2) Elimina previos por clave FIJA (sin traducción)
            for key in list(price_dict.keys()):
                if key in (WEAV_LOSS_KEY, PROD_LOSS_KEY, FINANCIAL_KEY, INCOTERM_KEY):
                    price_dict.pop(key, None)

            # 3) Calcula insumos y operaciones (tu lógica sin cambios)
            # ------------------------------------------------------------------
            pricing_pricelist = self._get_pricing_pricelist()
            if not pricing_pricelist:
                raise UserError(_('Configure a sales pricelist on the company or assign a pricelist to the order.'))
            order_pricelist = self.order_id.pricelist_id or pricing_pricelist
            pricing_currency = pricing_pricelist.currency_id
            currency = order_pricelist.currency_id or pricing_pricelist.currency_id
            conversion_date = self._get_order_date() or fields.Date.context_today(self)
            bom_id = self.bom_id or self.env['mrp.bom']
            weaving = self.has_weaving_operation #any(operation.operation_id.operation_type == 'weaving' for operation in self.operation_ids)
            thread_total = 0
            # Categorias de hilado: configuradas en la compania del pedido
            # (idetex, donde se cotiza). Usamos la compania del pedido para
            # reconocer los componentes de hilado de la LdM (determinista,
            # evita que env.company derive bajo sudo).
            thread_company = self.order_id.company_id or self.env.company
            thread_categs = thread_company.thread_category_ids

            def _compute_thread_signature():
                signature = []
                if not (weaving and self.order_id.sale_type == 'sale'):
                    return signature

                # Si es que el producto tiene LdM entonces se obtienen las fibras
                # de lo contrario pasamos a las fibras del análisis del producto
                if bom_id:
                    bom_lines = bom_id.bom_line_ids.filtered(lambda l: l.product_tmpl_id.categ_id in thread_categs)
                else:
                    bom_lines = self.product_template_id.analysis_id.weaving_data_ids.mapped('fiber_ids')
                for bom_line in bom_lines:
                    # Si el producto tiene LdM obtenemos la cantidad de lo contrario
                    # obtenemos la cantidad de las fibras del análisis del producto
                    # Aqui solo cambiamos el campo por ser otro modelo
                    if bom_id:
                        product = bom_line.product_id
                        quantity = bom_line.product_qty or 0
                    else:
                        product = bom_line.product_template_id
                        quantity = bom_line.percentage or 0
                    pricelist_item_id = pricing_pricelist._get_product_rule(
                        product,
                        quantity=quantity or 1.0,
                        uom=product.uom_id,
                        date=self._get_order_date(),
                    )
                    if pricelist_item_id:
                        bom_line_price = self.env['product.pricelist.item'].browse(pricelist_item_id)._compute_price(
                            product=product,
                            quantity=quantity or 1.0,
                            uom=product.uom_id,
                            date=self._get_order_date(),
                            currency=pricing_currency,
                        )
                        bom_line_price = self._convert_amount(
                            bom_line_price,
                            pricing_currency,
                            currency,
                            conversion_date,
                        )
                    else:
                        bom_line_price = self.env.company.currency_id._convert(
                            product.list_price,
                            currency,
                            self.env.company,
                            conversion_date,
                            round=False
                        )

                    qty = quantity
                    subtotal = float_round(bom_line_price * qty, 2)
                    signature.append((
                        product.id,
                        float_round(qty, 2),
                        subtotal,
                    ))

                return sorted(signature)

            current_meta = {
                'pricing_version': 2,
                'pricelist_id': pricing_pricelist.id,
                'order_pricelist_id': order_pricelist.id,
                'currency_id': currency.id,
                'pricing_date': str(conversion_date),
                'bom_id': bom_id.id,
                'product_color_id': self.product_color_id.id,
                'sale_type': self.order_id.sale_type,
                'thread_signature': _compute_thread_signature(),
            }

            saved_meta = price_dict.pop(META_KEY, None)
            # Invalidate cache only when pricing context truly changed.
            if saved_meta != current_meta:
                price_dict = {}
            if not price_dict:
                if weaving and self.order_id.sale_type == 'sale':
                    if bom_id:
                        bom_lines = bom_id.bom_line_ids.filtered(lambda l: l.product_tmpl_id.categ_id in thread_categs)
                    else:
                        bom_lines = self.product_template_id.analysis_id.weaving_data_ids.mapped('fiber_ids')
                    for bom_line in bom_lines:
                        if bom_id:
                            product = bom_line.product_id
                            quantity = bom_line.product_qty or 0
                        else:
                            product = bom_line.product_template_id
                            quantity = bom_line.percentage or 0
                        pricelist_item_id = pricing_pricelist._get_product_rule(
                            product,
                            quantity=quantity,
                            uom=product.uom_id,
                            date=self._get_order_date(),
                        )
                        if pricelist_item_id:
                            bom_line_price = self.env['product.pricelist.item'].browse(pricelist_item_id)._compute_price(
                                product=product,
                                quantity=quantity,
                                uom=product.uom_id,
                                date=self._get_order_date(),
                                currency=pricing_currency,
                            )
                            bom_line_price = self._convert_amount(
                                bom_line_price,
                                pricing_currency,
                                currency,
                                conversion_date,
                            )
                        else:
                            bom_line_price = self.env.company.currency_id._convert(
                                product.list_price,
                                currency,
                                self.env.company,
                                conversion_date,
                                round=False
                            )
                        qty = quantity
                        product_name = product.name
                        price_dict.setdefault(product_name, {
                            'label': product_name,
                            'price': 0.0,
                            'cost_per_kilo': 0.0,
                            'consumption_pct': 0.0,
                        })
                        price_dict[product_name]['price'] += float_round(bom_line_price * qty, 2)
                        price_dict[product_name]['consumption_pct'] += qty
                        # Asumimos costo uniforme por producto en una misma
                        # linea (varias bom_lines del mismo producto comparten
                        # precio). Si en el futuro hay precios distintos por
                        # bom_line, deberia ser un weighted avg.
                        price_dict[product_name]['cost_per_kilo'] = float_round(bom_line_price, 4)

                    for value in price_dict.values():
                        value['is_thread'] = True

                if not bom_id:
                    operations = self.product_template_id.analysis_id.routing_ids.sorted(key=lambda r: r.sequence).filtered(lambda l: l.operation_id.unit_price > 0 or l.operation_id.type_prices == 'col' and sum(l.operation_id.product_color_price_ids.mapped('unit_price')) > 0 or l.operation_id.operation_type == 'weaving')
                else:
                    operations = self.operation_ids.sorted(key=lambda r: r.sequence)

                for operation in operations:
                    if operation.operation_id.operation_type == 'weaving':
                        price = self._convert_amount(
                            self.product_template_id.analysis_id.weaving_price,
                            self.product_template_id.analysis_id.currency_id,
                            currency,
                            conversion_date,
                        )
                        price = float_round(price, 2)
                    else:
                        if operation.operation_id.type_prices == 'col':
                            operation_color_line = operation.operation_id.product_color_price_ids.search([
                                ('product_color_id', '=', self.product_color_id.id),
                                ('mrwo_id', '=', operation.operation_id._origin.id)
                            ])
                            if operation.operation_id.per_title:
                                operation_color_title_line = operation_color_line.color_title_price_ids.filtered(lambda l: self.product_template_id.analysis_id.product_title_id in l.title_ids)
                                source_currency = operation_color_title_line.currency_id if operation_color_title_line else operation.operation_id.currency_id
                                price = float_round(operation_color_title_line.unit_price, 2) if operation_color_title_line else 0
                            else:
                                source_currency = operation_color_line.currency_id if operation_color_line else operation.operation_id.currency_id
                                price = float_round(operation_color_line.unit_price, 2) if operation_color_line else 0
                        else:
                            source_currency = operation.operation_id.currency_id
                            price = float_round(operation.operation_id.unit_price, 2)
                        price = self._convert_amount(
                            price,
                            source_currency,
                            currency,
                            conversion_date,
                        )
                        price = float_round(price, 2)
                    if price:
                        price_dict[operation.operation_id.name] = {
                            'label': operation.operation_id.name,
                            'price': price,
                        }

            if self.printing_design_id:
                printing = price_dict.get('PRINTING')
                if not printing or printing.get('design_id') != self.printing_design_id.id or printing.get('qty') != self.product_uom_qty or printing.get('min_qty') != self.min_qty:
                    price_dict.pop('PRINTING', None)
                    if bom_id:
                        yield_meter = float_round(self.bom_id.technical_sheet_id.yield_meter if self.bom_id.technical_sheet_id else self.printing_design_id.yield_meter, 2)
                    else:
                        yield_meter = float_round(self.self.product_template_id.analysis_id.yield_meter if self.product_template_id.analysis_id else self.printing_design_id.yield_meter, 2)
                    if self.order_id.is_quote:
                        total_qty = round(self.min_qty * yield_meter)
                    else:
                        total_qty = round(self.product_uom_qty * yield_meter)
                    price = 0
                    if self.printing_design_id.printing_type == 'digital':
                        if total_qty > 59.99:
                            for price_line in self.printing_design_id.digital_unit_price_ids:
                                if total_qty >= price_line.min_qty and total_qty <= price_line.max_qty:
                                    price = float_round(price_line.unit_price * yield_meter, 2)
                                    price = self._convert_amount(
                                        price,
                                        price_line.currency_id,
                                        currency,
                                        conversion_date,
                                    )
                                    price = float_round(price, 2)
                        else:
                            price_line = self.printing_design_id.digital_unit_price_ids[:1]
                            price = price_line.unit_price if price_line else 0
                            if price_line:
                                price = self._convert_amount(
                                    price,
                                    price_line.currency_id,
                                    currency,
                                    conversion_date,
                                )
                                price = float_round(price, 2)
                    else:
                        price = float_round(self.printing_design_id.unit_price * yield_meter, 2)
                        price = self._convert_amount(
                            price,
                            self.printing_design_id.currency_id,
                            currency,
                            conversion_date,
                        )
                        price = float_round(price, 2)
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
            total = float_round(sum(v.get("price", 0.0) for v in price_dict.values() if isinstance(v, dict)), 2) if price_dict else 0

            if weaving:
                thread_total = float_round(sum(v.get('price', 0.0) for v in price_dict.values() if isinstance(v, dict) and v.get('is_thread')), 2) if price_dict else 0
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

            price_dict, total = self._apply_order_price_adjustments(
                price_dict,
                currency,
                conversion_date,
            )

            # 5) Guarda JSON con estructura {key: {"price": float, "label": str}}
            total = self._sum_price_items(price_dict)
            price_dict[META_KEY] = current_meta
            self.price_items = json.dumps(price_dict)

        # Si NO es cotización → tu lógica anterior (sin cambios)
        else:
            line = self.get_product_from_quote(self.product_id, self.product_color_id, self.bom_id, self.printing_design_id)
            self.bom_id = line.bom_id
            if line:
                source_currency = line.order_id.pricelist_id.currency_id or line.currency_id
                order_pricelist = self.order_id.pricelist_id or self._get_pricing_pricelist()
                target_currency = order_pricelist.currency_id or self.currency_id
                conversion_date = self._get_order_date() or fields.Date.context_today(self)
                source_price_dict = self._load_price_items_dict(line.price_items)
                if source_price_dict:
                    copied_price_dict = self._copy_price_items_to_currency(
                        source_price_dict,
                        source_currency,
                        target_currency,
                        conversion_date,
                    )
                    copied_price_dict, total = self._apply_order_price_adjustments(
                        copied_price_dict,
                        target_currency,
                        conversion_date,
                    )
                    copied_price_dict[META_KEY] = {
                        'source_order_id': line.order_id.id,
                        'source_line_id': line.id,
                        'currency_id': target_currency.id,
                        'payment_term_id': self.order_id.payment_term_id.id,
                        'incoterm_id': self.order_id.incoterm.id,
                        'pricing_date': str(conversion_date),
                    }
                    self.price_items = json.dumps(copied_price_dict)
                else:
                    total = self._convert_amount(line.price_unit, source_currency, target_currency, conversion_date)
            else:
                total = 1

        return float_round(total, 2)
    
    def get_product_from_quote(self, product, color, bom, printing_design_id):
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
            ('order_id.is_quote', '=', True),
            ('operation_ids','=', self.operation_ids.ids),
            ('order_id.state', '=', 'sent'),
            ('order_id.signed_on', '!=', False),
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
            if 'product_uom_qty' in vals and rec.production_id and rec.production_id.state == 'draft':
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

    def action_duplicate_without_color(self):
        """Duplica la linea actual dejando product_color_id vacio.

        Util para repetir el mismo producto con otro color sin tener que
        recrear toda la linea (cantidades, precios, etc.). Tenemos que
        pasar `order_id` explicito porque Odoo lo marca como copy=False
        en sale.order.line (las copias no caen a otra orden por default).
        """
        self.ensure_one()
        self.copy(default={
            'order_id': self.order_id.id,
            'product_color_id': False,
            'color_name': False,
            'lab_dev_line_id': False,
        })

    def _get_sale_order_line_multiline_description_sale(self):
        self.ensure_one()
        if self.product_id and self.product_id.is_weaving and self.company_id.is_company_produce:
            description = (self.product_id.name or '') + self._get_sale_order_line_multiline_description_variants()
            if self.linked_line_id and not self.combo_item_id:
                description += "\n" + _(
                    "Option for: %s",
                    self.linked_line_id.product_id.with_context(display_default_code=False).display_name,
                )
            return description
        return super()._get_sale_order_line_multiline_description_sale()
    
class SaleOrderLineSize(models.Model):
    _name = 'sale.order.line.size'
    _description = 'Sale Order Line Size'

    line_id = fields.Many2one('sale.order.line', string='Sale Order Line', required=True, ondelete="cascade")
    sequence = fields.Integer(default=10)
    size = fields.Char(string='Size')
    product_qty = fields.Integer('Product Qty', required=True, default=0)
    # length = fields.Float(string="Largo (cm)")
    # width = fields.Float(string="Ancho (cm)")