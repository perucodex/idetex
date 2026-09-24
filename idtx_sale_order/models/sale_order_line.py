import logging

from odoo import models, fields, api, _, Command
from odoo.tools import float_round, float_compare, float_is_zero
from odoo.exceptions import UserError
import json

_logger = logging.getLogger(__name__)

META_KEY = "__price_meta__"
WEAV_LOSS_KEY = "Weaving Loss"
PROD_LOSS_KEY = "Production Loss"
FINANCIAL_KEY = "Financial Percentage"
INCOTERM_KEY = "Incoterm"
SAMPLE_KEY = "Sample"

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
    # Semáforo del diseño en la línea (cotización y pedido): rojo sin diseño,
    # naranja ficha sin precio o sin cerrar, verde ficha Hecha con precio.
    printing_design_state = fields.Selection(related='printing_design_id.state')
    printing_design_has_price = fields.Boolean(related='printing_design_id.has_price')
    analysis_id = fields.Many2one(related='product_template_id.analysis_id')
    # Semáforo de producción del producto (estado a nivel de ANÁLISIS, JP
    # 21-sep-2026): rojo sin letra = sin OF; rojo M = muestra en curso; verde
    # M = muestra terminada; naranja P = piloto en curso; verde P = piloto
    # terminado; verde sin letra = OF de venta/servicio terminada. Lo pinta
    # analysis_production_state_widget.
    analysis_production_indicator = fields.Selection(
        related='product_template_id.analysis_id.production_indicator')
    # 'Ficha' (pedido de JP, sep-2026): en ventas la LdM se llama ficha técnica.
    # Desde 21-sep-2026 la ficha YA NO se elige en la cotización (oculta en la
    # vista): los procesos a cotizar salen de la RUTA DEL ANÁLISIS del producto.
    # Se sigue asignando sola (primera LdM del producto) porque la OF la necesita.
    bom_id = fields.Many2one('mrp.bom', string='Ficha')
    # Operaciones cotizadas: fases del MAESTRO (mrp.routing.workcenter.operation)
    # tomadas de la ruta del análisis del producto (antes eran las operaciones
    # de la LdM, mrp.routing.workcenter). En servicio el vendedor puede quitar.
    operation_ids = fields.Many2many(
        'mrp.routing.workcenter.operation',
        'sale_order_line_mrwo_rel', 'line_id', 'operation_id',
        string='Operations')
    # lab_dev_ids = fields.Many2many(related='order_id.lab_dev_ids', store=True)
    available_operation_ids = fields.Many2many(
        'mrp.routing.workcenter.operation',
        compute='_compute_available_operations',
        string='Available Operations'
    )
    # Ids de las fases de la ruta del análisis en orden de secuencia (JSON):
    # el widget route_ordered_many2many_tags pinta las Operaciones siempre en
    # ese orden, aunque se quiten y vuelvan a agregar (JP, 22-sep-2026).
    route_operation_order = fields.Char(compute='_compute_route_operation_order')
    # Campo para guardar los precios
    price_items = fields.Text(string='Price Items', default='{}')
    # Antes era Many2one y la reposición "reemplazaba" la OF de la línea.
    # Ahora la línea lista TODAS sus OFs (la original y sus reposiciones):
    # inverso de mrp.production.sale_order_line_id.
    production_ids = fields.One2many(
        'mrp.production', 'sale_order_line_id',
        string='Órdenes de Fabricación', copy=False)
    parent_is_quote = fields.Boolean(related='order_id.is_quote')
    parent_is_company_produce = fields.Boolean(related='order_id.is_company_produce')
    has_approved_lab_line = fields.Boolean(
        string='Approved',
        compute='_compute_has_approved_lab_line',
        store=False,
    )
    lab_dev_line_id = fields.Many2one('lab.dev.line', string='Lab Dip Line')
    diff_days = fields.Float('diff_days')
    is_salesman = fields.Boolean('is_salesman?', compute='_compute_is_salesman')
    # Fechas de precio de los procesos cotizados (JSON) para el widget del
    # VENDEDOR process_price_dates_widget, que ocupa el lugar del "Editar
    # precios" (solo admin de ventas): procesos y fecha de última actualización
    # de su precio, sin importes, sin hilado y sin mermas (JP, 23-sep-2026).
    process_price_info = fields.Text(compute='_compute_process_price_info')
    # Recargo de muestra de la línea en la moneda del pedido (0 si el pedido no
    # es Muestra). Lo lee el popover "Editar precios" para pintar la fila
    # Muestra; el precio se aplica en _apply_order_price_adjustments.
    sample_surcharge = fields.Float(compute='_compute_sample_surcharge', digits='Product Price')
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

    # ------------------------------------------------------------------
    # Ruta del análisis del producto (fuente de los procesos a cotizar)
    # ------------------------------------------------------------------
    def _get_analysis_route_operations(self):
        """Fases (maestro) de la ruta del análisis del producto, en el orden
        de la ruta y sin repetidos. Lectura con sudo: el comercial no
        necesita permisos de Fabricación para cotizar."""
        self.ensure_one()
        analysis = self.sudo().product_template_id.analysis_id
        lines = analysis.routing_ids.sorted(key=lambda r: (r.sequence, r.id))
        return lines.mapped('operation_id')

    @api.model
    def _filter_priced_operations(self, operations):
        """Fases que aportan al precio: con precio por proceso, por color
        (o por color y título), la de tejido (su precio sale del análisis) y
        las que ESTAMPAN el producto (toggle prints_product; su precio va
        aparte, con el diseño: siempre se muestran aunque su precio por
        proceso sea 0; JP, 22-sep-2026). Las auxiliares sin precio (control
        de peso, calidad, cepillado, vaporizado…) no se cotizan."""
        def priced(op):
            if op.operation_type == 'weaving' or op.prints_product or op.unit_price > 0:
                return True
            if op.type_prices == 'col':
                if sum(op.product_color_price_ids.mapped('unit_price')) > 0:
                    return True
                if op.per_title and sum(
                        op.product_color_price_ids.color_title_price_ids.mapped('unit_price')) > 0:
                    return True
            return False
        return operations.filtered(priced)

    def _get_priced_route_operations(self):
        self.ensure_one()
        return self._filter_priced_operations(self._get_analysis_route_operations())

    def _get_quoted_operations(self):
        """Operaciones a cotizar de la línea: las seleccionadas (operation_ids),
        en el orden de la ruta del análisis; si aún no hay selección, toda la
        ruta con precio. Una fase seleccionada que ya no esté en la ruta se
        conserva al final (se cotizó así)."""
        self.ensure_one()
        selected = self.sudo().operation_ids._origin
        if not selected:
            return self._get_priced_route_operations()
        route = self._get_analysis_route_operations()
        return route.filtered(lambda op: op in selected) | (selected - route)

    @api.depends(
        'operation_ids',
        'operation_ids.operation_type',
        'product_template_id',
        'product_template_id.analysis_id',
        'product_template_id.analysis_id.routing_ids',
        'product_template_id.analysis_id.routing_ids.operation_id',
        'product_template_id.analysis_id.routing_ids.operation_id.operation_type',
    )
    def _compute_has_weaving_operation(self):
        for line in self:
            # Si el vendedor ya eligió operaciones (p. ej. servicio sin
            # tejido) mandan esas; si no, la ruta del análisis del producto.
            sline = line.sudo()
            operations = sline.operation_ids._origin
            if not operations and sline.product_template_id:
                operations = line._get_analysis_route_operations()
            line.has_weaving_operation = any(
                op.operation_type == "weaving" for op in operations)

    @api.onchange('printing_design_id')
    def _onchange_printing_design_id(self):
        for rec in self:
            # El rendimiento (m/kg) es del análisis del producto (la ficha lo
            # tomaba de ahí); sin análisis se usa el del diseño.
            analysis = rec.sudo().product_template_id.analysis_id
            yield_meter = analysis.yield_meter if analysis else rec.printing_design_id.yield_meter
            # Sin rendimiento no se puede derivar la cantidad mínima: se avisa
            # en lugar de dividir por cero (antes reventaba con ZeroDivisionError).
            if rec.printing_design_id and not yield_meter:
                rec.min_qty = 1000
                return {'warning': {
                    'title': _('Falta el rendimiento'),
                    'message': _(
                        'El diseño %s no tiene rendimiento (kg) y la ficha '
                        'técnica tampoco: la cantidad mínima queda en 1000. '
                        'Complétalo en el diseño de estampado.',
                        rec.printing_design_id.display_name),
                }}
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

    # ------------------------------------------------------------------
    # Fechas de precio de los procesos (widget del vendedor)
    # ------------------------------------------------------------------
    def _process_price_row(self, name, date, has_price, missing):
        if date:
            date_display = fields.Datetime.context_timestamp(self, date).strftime('%d/%m/%Y %H:%M')
        elif has_price:
            date_display = _('Sin fecha registrada')
        else:
            date_display = missing
        return {
            'name': name,
            'date': fields.Datetime.to_string(date) if date else False,
            'date_display': date_display,
            'has_price': has_price,
        }

    def _get_process_price_rows(self):
        """Procesos cotizados de la línea (mismo orden que el popover de
        precios) con la fecha de última actualización de su precio: tejido =
        precio de tejido del análisis; por color (y título) = la fila de
        precio del color/título; por proceso = la fase; estampado = la ficha
        del diseño, fusionada en la fase que estampa (una fila por proceso).
        Sin hilado ni mermas: es la vista del vendedor, que no ve importes.
        Lectura con sudo: ventas no tiene permisos de Fabricación."""
        self.ensure_one()
        line = self.sudo()
        analysis = line.product_template_id.analysis_id
        design = line.printing_design_id
        design_date = design and (design.price_date or (design.write_date if design.has_price else False))
        rows, printing_merged = [], False
        for op in self._get_quoted_operations().sudo():
            if op.operation_type == 'weaving':
                has_price = analysis.weaving_price > 0
                date = analysis.weaving_price_date or (analysis.write_date if has_price else False)
                missing = _('Sin precio de tejido en el análisis')
            elif op.type_prices == 'col':
                rec = op.product_color_price_ids.filtered(
                    lambda p: p.product_color_id == line.product_color_id)[:1]
                if op.per_title:
                    rec = rec.color_title_price_ids.filtered(
                        lambda t: analysis.product_title_id in t.title_ids)[:1]
                has_price = bool(rec) and rec.unit_price > 0
                date = rec.write_date if has_price else False
                missing = _('Sin precio para el color') if not line.product_color_id or not op.per_title \
                    else _('Sin precio para el color y título')
            else:
                has_price = op.unit_price > 0
                date = (op.price_date or op.write_date) if has_price else False
                missing = _('Sin precio')
            if op.prints_product and design:
                # La fase que estampa cobra con la ficha del diseño: una sola fila.
                printing_merged = True
                has_price = has_price or design.has_price
                dates = [d for d in (date, design_date) if d]
                date = max(dates) if dates else False
                missing = _('Ficha de estampado sin precio')
            rows.append(self._process_price_row(op.name, date, has_price, missing))
        if design and not printing_merged:
            rows.append(self._process_price_row(
                _('PRINTING'), design_date, design.has_price, _('Ficha de estampado sin precio')))
        return rows

    @api.depends('operation_ids', 'product_template_id', 'product_color_id', 'printing_design_id',
                 'display_type',
                 'product_template_id.analysis_id.weaving_price',
                 'product_template_id.analysis_id.weaving_price_date',
                 'product_template_id.analysis_id.routing_ids.operation_id',
                 'printing_design_id.price_date', 'printing_design_id.has_price')
    def _compute_process_price_info(self):
        for line in self:
            rows = []
            if line.product_template_id and not line.display_type:
                rows = line._get_process_price_rows()
            line.process_price_info = json.dumps(rows)

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
                 'lab_dev_line_id.color_recipe_ids.recipe_lot_ids.state',
                 'lab_dev_line_id.color_recipe_ids.recipe_lot_ids.lot_ids',
                 'lab_dev_line_id.color_recipe_ids.recipe_lot_ids.production_id',
                 'product_template_id', 'production_ids')
    def _compute_has_approved_lab_line(self):
        # El badge del color es verde si la línea de Lab Dip tiene una receta
        # APROBADA que incluya al PRODUCTO de esta línea de venta (receta
        # individual o de combinación), o bien —TELA DEL CLIENTE (servicio sin
        # tejido, JP 18-sep-2026)— si alguna receta aprobada del color tiene
        # VALIDADA la sub-receta sin lotes de una OF de esta línea: la tela
        # del cliente no figura entre los productos de la receta.
        for line in self:
            recipes = line.lab_dev_line_id.color_recipe_ids.filtered(
                lambda cr: cr.state == 'approved') if line.lab_dev_line_id else []
            ok = any(line.product_template_id in cr.product_ids for cr in recipes)
            if not ok and recipes:
                prods = line.production_ids.filtered(
                    lambda p: p.state != 'cancel' and p.is_customer_roll_production)
                ok = bool(prods) and any(
                    sub.state == 'validated' and not sub.lot_ids
                    and sub.production_id in prods
                    for cr in recipes for sub in cr.recipe_lot_ids)
            line.has_approved_lab_line = ok

    @api.depends(
        'product_template_id',
        'product_template_id.analysis_id',
        'product_template_id.analysis_id.routing_ids',
        'product_template_id.analysis_id.routing_ids.operation_id',
        'product_template_id.analysis_id.routing_ids.operation_id.gives_color',
    )
    def _compute_is_lab_color(self):
        for line in self:
            line.is_lab_color = any(
                op.gives_color for op in line._get_analysis_route_operations()
            ) if line.product_template_id else False

    @api.depends(
        'product_template_id',
        'product_template_id.analysis_id',
        'product_template_id.analysis_id.routing_ids',
        'product_template_id.analysis_id.routing_ids.operation_id',
        'product_template_id.analysis_id.routing_ids.operation_id.operation_type',
        'product_template_id.analysis_id.routing_ids.operation_id.unit_price',
        'product_template_id.analysis_id.routing_ids.operation_id.type_prices',
        'product_template_id.analysis_id.routing_ids.operation_id.per_title',
        'product_template_id.analysis_id.routing_ids.operation_id.product_color_price_ids.unit_price',
        'product_template_id.analysis_id.routing_ids.operation_id.product_color_price_ids.color_title_price_ids.unit_price',
    )
    def _compute_available_operations(self):
        for record in self:
            record.available_operation_ids = record._get_priced_route_operations() \
                if record.product_template_id else self.env['mrp.routing.workcenter.operation']

    @api.depends(
        'product_template_id',
        'product_template_id.analysis_id',
        'product_template_id.analysis_id.routing_ids',
        'product_template_id.analysis_id.routing_ids.sequence',
        'product_template_id.analysis_id.routing_ids.operation_id',
    )
    def _compute_route_operation_order(self):
        for record in self:
            ops = record._get_analysis_route_operations() if record.product_template_id else []
            record.route_operation_order = json.dumps([op.id for op in ops])

    @api.depends(
        'operation_ids',
        'operation_ids.prints_product',
        'product_template_id',
        'product_template_id.analysis_id',
        'product_template_id.analysis_id.routing_ids',
        'product_template_id.analysis_id.routing_ids.operation_id',
        'product_template_id.analysis_id.routing_ids.operation_id.prints_product',
    )
    def _compute_is_printing(self):
        """Estampa si hay una fase que ESTAMPA el producto (toggle
        prints_product de la fase, no el tipo 'printing': en ese centro hay
        muchas auxiliares) entre las operaciones elegidas (servicio: el
        vendedor puede quitarla) o, sin selección, en la ruta del análisis.
        Esas fases siempre son seleccionables (su precio va con el diseño),
        así que quitarla = no estampar."""
        for rec in self:
            sline = rec.sudo()
            operations = sline.operation_ids._origin
            if not operations and sline.product_template_id:
                operations = rec._get_analysis_route_operations()
            rec.is_printing = any(op.prints_product for op in operations)

    @api.onchange('product_id', 'product_color_id')
    def _onchange_route_operations(self):
        """Propone como operaciones a cotizar todas las fases con precio de la
        ruta del análisis del producto (en servicio el vendedor puede quitar)."""
        for rec in self:
            rec.operation_ids = [Command.set(rec._get_priced_route_operations().ids)]

    @api.onchange('operation_ids')
    def _onchange_operation_ids_printing(self):
        """Servicio: al quitar la fase de estampado la línea deja de estampar y
        se limpia el diseño (su recargo sale del precio; min_qty vuelve a 1000
        por el onchange del diseño)."""
        for rec in self:
            if rec.printing_design_id and not rec.is_printing:
                rec.printing_design_id = False

    @api.onchange('product_id', 'bom_id')
    def _onchange_bom_id(self):
        for rec in self:
            # Mermas: de la ficha técnica de la LdM asignada; sin ficha, los
            # valores por defecto (1% tejido, 9% producción). Lectura con sudo
            # (datos de producción que el comercial puede no leer).
            srec = rec.sudo()
            rec.weaving_loss = srec.bom_id.technical_sheet_id.scrap or 0.01
            rec.production_loss = srec.bom_id.technical_sheet_id.prod_scrap or 0.09
            for prd in rec.production_ids.filtered(
                    lambda p: p.state not in ('done', 'cancel')):
                prd.bom_id = rec.bom_id

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
            prods = rec.production_ids.filtered(lambda p: p.state != 'cancel')
            if rec.lab_dev_line_id and rec.lab_dev_line_id.state == 'approved' and prods:
                if any(wo.state == 'progress' for wo in prods.workorder_ids.filtered(lambda wo: wo.mrwo_id.use_lab_recipe)):
                    raise UserError(_('Cannot change recipe because there are workorders in progress using the lab recipe.'))
                for prd in prods:
                    prd.color_recipe_id = rec.lab_dev_line_id.color_recipe_ids.filtered(
                        lambda cr: cr.state == 'approved' and prd.product_tmpl_id in cr.product_ids)[:1]

    @api.onchange('product_id')
    def _onchange_product_id(self):
        res = super()._onchange_product_id()
        # La ficha (LdM) no se elige en la cotización: se toma la primera del
        # producto para que la OF del pedido la tenga. Si el producto no tiene
        # LdM (o no es tejido) se limpia para no arrastrar la de otro producto.
        self.bom_id = self.sudo().product_template_id.bom_ids[:1] if self.is_weaving else False
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
                 'order_id.is_sample',
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

    # ------------------------------------------------------------------
    # Recargo de muestra (pedido marcado como Muestra)
    # ------------------------------------------------------------------
    def _get_sample_label(self):
        self.ensure_one()
        return _('Muestra de estampado') if self._is_printing_sample() else _('Muestra')

    def _is_printing_sample(self):
        """Línea de estampado para el recargo de muestra: su ruta estampa el
        producto (is_printing) o ya tiene diseño de estampado elegido."""
        self.ensure_one()
        return bool(self.is_printing or self.printing_design_id)

    def _get_sample_surcharge(self, currency, conversion_date=None):
        """Recargo de muestra de la línea en `currency`; 0 si el pedido no está
        marcado como Muestra. La línea CON diseño de estampado usa el precio de
        muestra estampado, el resto el precio de muestra. Manda el precio del
        cliente (o de su empresa comercial) si es mayor a 0; si no, el de la
        configuración de la compañía del pedido. Ambos están en la moneda de
        muestras de la compañía (sample_currency_id)."""
        self.ensure_one()
        order = self.order_id
        if not order.is_sample:
            return 0.0
        field = 'sample_printing_price' if self._is_printing_sample() else 'sample_price'
        company = order.company_id or self.env.company
        partner = order.partner_id.sudo()
        amount = 0.0
        for candidate in (partner, partner.commercial_partner_id):
            if candidate and candidate[field] > 0:
                amount = candidate[field]
                break
        else:
            amount = company[field]
        if not amount:
            return 0.0
        return float_round(self._convert_amount(
            amount, company.sample_currency_id, currency,
            conversion_date or self._get_order_date() or fields.Date.context_today(self)), 2)

    @api.depends('order_id.is_sample', 'order_id.partner_id', 'order_id.pricelist_id',
                 'order_id.company_id', 'printing_design_id', 'is_printing')
    def _compute_sample_surcharge(self):
        for line in self:
            if not line.order_id.is_sample:
                line.sample_surcharge = 0.0
                continue
            pricelist = line.order_id.pricelist_id or line._get_pricing_pricelist()
            currency = pricelist.currency_id or line.currency_id
            line.sample_surcharge = line._get_sample_surcharge(currency)

    def _apply_order_price_adjustments(self, price_dict, currency, conversion_date):
        self.ensure_one()
        adjusted_dict = {}
        for key, value in (price_dict or {}).items():
            if key in (SAMPLE_KEY, FINANCIAL_KEY, INCOTERM_KEY):
                continue
            adjusted_dict[key] = value

        total = self._sum_price_items(adjusted_dict)

        # Recargo de muestra (JP, 23-sep-2026): se suma al precio del producto
        # antes del % financiero (que financia el total) y del incoterm.
        sample = self._get_sample_surcharge(currency, conversion_date)
        if sample:
            adjusted_dict[SAMPLE_KEY] = {
                'price': sample,
                'label': self._get_sample_label(),
            }
            total = float_round(total + sample, 2)

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

            # 2) Elimina previos por clave FIJA (sin traducción). SAMPLE_KEY
            # también: si quedara, la merma de producción se calcularía sobre
            # base + muestra; el recargo de muestra va DESPUÉS de las mermas.
            for key in list(price_dict.keys()):
                if key in (WEAV_LOSS_KEY, PROD_LOSS_KEY, SAMPLE_KEY, FINANCIAL_KEY, INCOTERM_KEY):
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

                # Procesos a cotizar: fases del maestro tomadas de la RUTA DEL
                # ANÁLISIS del producto (ya no de la ficha/LdM), en su orden.
                for operation in self._get_quoted_operations():
                    if operation.operation_type == 'weaving':
                        price = self._convert_amount(
                            self.product_template_id.analysis_id.weaving_price,
                            self.product_template_id.analysis_id.currency_id,
                            currency,
                            conversion_date,
                        )
                        price = float_round(price, 2)
                    else:
                        if operation.type_prices == 'col':
                            operation_color_line = operation.product_color_price_ids.filtered(
                                lambda p: p.product_color_id == self.product_color_id)[:1]
                            if operation.per_title:
                                operation_color_title_line = operation_color_line.color_title_price_ids.filtered(lambda l: self.product_template_id.analysis_id.product_title_id in l.title_ids)[:1]
                                source_currency = operation_color_title_line.currency_id if operation_color_title_line else operation.currency_id
                                price = float_round(operation_color_title_line.unit_price, 2) if operation_color_title_line else 0
                            else:
                                source_currency = operation_color_line.currency_id if operation_color_line else operation.currency_id
                                price = float_round(operation_color_line.unit_price, 2) if operation_color_line else 0
                        else:
                            source_currency = operation.currency_id
                            price = float_round(operation.unit_price, 2)
                        price = self._convert_amount(
                            price,
                            source_currency,
                            currency,
                            conversion_date,
                        )
                        price = float_round(price, 2)
                    if price:
                        price_dict[operation.name] = {
                            'label': operation.name,
                            'price': price,
                        }

            if self.printing_design_id:
                printing = price_dict.get('PRINTING')
                # force_printing_reprice: la ficha cambió de precio (pasó a Hecho);
                # el recargo guardado ya no vale aunque diseño y cantidades coincidan.
                # Autocuración: si el recargo guardado es 0 (se calculó con la ficha
                # del vendedor aún sin precio) y la ficha ya tiene precio, se rehace.
                stale_zero = printing and not printing.get('price') and self.printing_design_id.has_price
                if not printing or stale_zero or self.env.context.get('force_printing_reprice') or printing.get('design_id') != self.printing_design_id.id or printing.get('qty') != self.product_uom_qty or printing.get('min_qty') != self.min_qty:
                    price_dict.pop('PRINTING', None)
                    # Rendimiento (m/kg) del análisis del producto (la ficha lo
                    # tomaba de ahí); sin análisis, el del diseño.
                    analysis = self.product_template_id.analysis_id
                    yield_meter = float_round(analysis.yield_meter if analysis else self.printing_design_id.yield_meter, 2)
                    if self.order_id.is_quote:
                        total_qty = round(self.min_qty * yield_meter)
                    else:
                        total_qty = round(self.product_uom_qty * yield_meter)
                    price = 0
                    if self.printing_design_id.printing_type == 'digital':
                        # Rango por metros totales; por debajo del primer rango (o sin
                        # cantidad) se usa el primero. En TODOS los rangos, también el
                        # primero, el recargo es (precio + bondeo) * rendimiento: antes
                        # el primer rango trasladaba el precio plano (JP, 22-sep-2026).
                        price_lines = self.printing_design_id.digital_unit_price_ids.sorted('sequence')
                        price_line = price_lines.filtered(lambda p: p.min_qty <= total_qty <= p.max_qty)[:1] or price_lines[:1]
                        if price_line:
                            price = float_round((price_line.unit_price + self.printing_design_id.bonding_price) * yield_meter, 2)
                            price = self._convert_amount(
                                price,
                                price_line.currency_id,
                                currency,
                                conversion_date,
                            )
                            price = float_round(price, 2)
                    else:
                        # El precio de estampado por kg suma el bondeo (ambos son precios por metro)
                        # antes de multiplicar por el rendimiento: (precio + bondeo) * rendimiento.
                        price = float_round((self.printing_design_id.unit_price + self.printing_design_id.bonding_price) * yield_meter, 2)
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
            line = self.env['sale.order.line']
            # Solo se toma la cotización vinculada si es del mismo tipo de
            # venta y de la misma condición de Muestra (JP, 23-sep-2026): un
            # pedido de muestra toma el precio de una cotización de muestra y
            # uno normal de una normal. Si difiere, se cae al fallback, que
            # filtra por ambos criterios.
            if quote.sale_type == self.order_id.sale_type and quote.is_sample == self.order_id.is_sample:
                line = quote.order_line.filtered(lambda l: l.product_id == product and l.product_color_id == color)
            if not line:
                today = fields.Date.context_today(self)
                line = self._get_last_quotation_price(today)
                if line:
                    if line.order_id.validity_date <= today:
                        self.diff_days = (today - line.order_id.validity_date ).days
                    return line
                elif self.order_id.is_sample:
                    raise UserError(_(
                        'El producto %s con color %s no está en ninguna cotización de MUESTRA firmada '
                        'de este cliente. Un pedido de muestra toma el precio de una cotización de muestra: '
                        'cotízalo primero como muestra.', product.name, color.name))
                else:
                    raise UserError(_(
                        'El producto %s con color %s no está en ninguna cotización firmada de este cliente '
                        '(sin contar las de muestra). Cotízalo primero.', product.name, color.name))
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
            ('order_id.sale_type', '=', self.order_id.sale_type),
            # Misma condición de Muestra que el pedido (JP, 23-sep-2026).
            ('order_id.is_sample', '=', self.order_id.is_sample),
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
    
    def _check_line_unlink(self):
        # Una línea en 0, sin facturar y sin entregas, es una línea anulada
        # (su OF ya se eliminó al ponerla en 0): se puede eliminar aunque el
        # pedido esté confirmado, a diferencia del bloqueo estándar del core.
        undeletable = super()._check_line_unlink()
        deletable_zero = undeletable.filtered(
            lambda l: float_is_zero(
                l.product_uom_qty, precision_rounding=l.product_uom_id.rounding or 0.001)
            and not l.invoice_lines
            and float_is_zero(
                l.qty_delivered, precision_rounding=l.product_uom_id.rounding or 0.001)
        )
        return undeletable - deletable_zero

    def unlink(self):
        # Al eliminar una línea anulada (cantidad 0), su movimiento de
        # entrega en 0 no debe quedar huérfano en el picking: se cancela y
        # elimina. Solo llegan aquí líneas eliminables (_check_line_unlink),
        # cuyos movimientos vivos ya están en demanda 0.
        moves = self.sudo().move_ids.filtered(lambda m: m.state != 'done')
        res = super().unlink()
        if moves:
            moves.filtered(lambda m: m.state != 'cancel')._action_cancel()
            moves.unlink()
        return res

    def _production_qty_from_sale_qty(self, sale_qty):
        """Cantidad a FABRICAR para entregar sale_qty: se infla por la merma de
        producción de la línea con la misma convención que el precio
        (qty / (1 - merma)); con 9% de merma, 500 kg pedidos -> 549.45 kg.
        Redondeo a la precisión de la UdM. La entrega al cliente sigue siendo
        la cantidad pedida."""
        self.ensure_one()
        loss = self.production_loss or self.sudo().bom_id.technical_sheet_id.prod_scrap or 0.0
        if not sale_qty or loss <= 0 or loss >= 1:
            return sale_qty
        return float_round(sale_qty / (1 - loss),
                           precision_rounding=self.product_uom_id.rounding or 0.01)

    def _create_weaving_productions(self):
        """Crea la OF de cada línea de tejido con LdM (mismas reglas que la
        confirmación del pedido). Se usa al confirmar el pedido y al agregar
        una línea a un pedido ya confirmado. Devuelve las OF creadas."""
        productions = self.env['mrp.production'].sudo()
        for line in self:
            if not (line.product_uom_qty and line.product_id.is_weaving and line.bom_id):
                continue
            order = line.order_id
            production_company = order.company_id._get_production_company()
            prd = self.env['mrp.production'].sudo().with_company(production_company).create({
                'product_tmpl_id': line.product_id.product_tmpl_id.id,
                'product_qty': line._production_qty_from_sale_qty(line.product_uom_qty),
                'bom_id': line.bom_id.id,
                'sale_order_line_id': line.id,
                'production_type': order.sale_type,
                'company_id': production_company.id,
            })
            # La línea "ve" la OF por el o2m inverso de sale_order_line_id.
            order.sudo().production_ids = [(4, prd.id)]
            # Se confirma sola si el color de DESARROLLO del pedido ya está
            # aprobado (misma regla que action_confirm; la receta de
            # producción la valida la partida) Y el producto ya tiene PILOTO
            # terminado (estado de producción del análisis). Si no, queda en
            # borrador con el botón Confirmar para cuando laboratorio apruebe
            # el color o termine el piloto.
            if line.lab_dev_line_id.state == 'approved' and prd._production_state_allows_confirm():
                prd.action_confirm()
            prd.do_unreserve()
            productions |= prd
        return productions

    def _link_printing_design_to_quotation(self):
        """La ficha de estampado en borrador creada por el vendedor queda
        enlazada a la cotización donde se usó por primera vez (trazabilidad)."""
        for line in self.filtered(lambda l: l.printing_design_id and l.order_id.is_quote and l.order_id.id):
            design = line.printing_design_id
            if design.state == 'draft' and not design.quotation_id:
                design.quotation_id = line.order_id.id

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        # Producto agregado a un pedido YA confirmado: crear su OF con las
        # mismas reglas que la confirmación (la entrega la ajusta el core
        # por las reglas de stock).
        lines.filtered(lambda l: l.order_id.state == 'sale')._create_weaving_productions()
        lines._link_printing_design_to_quotation()
        return lines

    def write(self, vals):
        if 'product_uom_qty' in vals:
            for rec in self:
                rounding = rec.product_uom_id.rounding or 0.001
                if float_compare(vals['product_uom_qty'], rec.product_uom_qty,
                                 precision_rounding=rounding) == 0:
                    continue
                # La OF fabrica la cantidad pedida inflada por la merma.
                new_prod_qty = rec._production_qty_from_sale_qty(vals['product_uom_qty'])
                for prd in rec.production_ids.filtered(
                        lambda p: p.state not in ('done', 'cancel')):
                    # OF ya iniciada: no se permite cambiar la cantidad (y al
                    # abortar aquí tampoco se toca la entrega).
                    if prd.state in ('progress', 'to_close') or any(
                            wo.state in ('progress', 'done') for wo in prd.workorder_ids):
                        raise UserError(_(
                            'No se puede actualizar la cantidad: la OF %(mo)s '
                            'ya inició su primera operación.',
                            mo=prd.display_name))
                    if float_is_zero(vals['product_uom_qty'], precision_rounding=rounding):
                        # Cantidad en 0: la OF sin iniciar se elimina (el
                        # asistente del core no acepta cantidad 0).
                        prd_su = prd.sudo()
                        if prd_su.state != 'draft':
                            prd_su.action_cancel()
                        prd_su.unlink()
                    elif prd.state == 'draft':
                        prd.sudo().product_qty = new_prod_qty
                    else:
                        # OF confirmada: el asistente estándar ajusta consumos
                        # y órdenes de trabajo.
                        self.env['change.production.qty'].sudo().with_company(prd.company_id).create({
                            'mo_id': prd.id,
                            'product_qty': new_prod_qty,
                        }).change_prod_qty()
        res = super().write(vals)
        if 'product_uom_qty' in vals:
            # Cantidad repuesta (>0) en una línea de pedido confirmado que ya
            # no tiene OF (p.ej. se puso en 0 y su OF se eliminó): recrearla.
            # Si existe alguna OF hecha/activa no se crea otra.
            self.filtered(
                lambda l: l.order_id.state == 'sale' and l.product_uom_qty
                and not l.production_ids.filtered(lambda p: p.state != 'cancel')
            )._create_weaving_productions()
        # Servicio: al quitar la fase de estampado de las operaciones la línea
        # deja de estampar y su diseño se limpia (JP, 22-sep-2026); el write
        # anidado recalcula el precio sin el recargo de estampado.
        if 'operation_ids' in vals:
            to_clear = self.filtered(lambda l: l.printing_design_id and not l.is_printing)
            if to_clear:
                to_clear.write({'printing_design_id': False})
        # El recargo de estampado se calcula con el precio del tejido, pero el
        # diseño solo se puede elegir en el PEDIDO: sin este recálculo el pedido
        # quedaba con diseño asignado y un precio que no lo incluía.
        if 'printing_design_id' in vals and not self.env.context.get('skip_printing_reprice'):
            self._reprice_printing_lines()
        if vals.get('printing_design_id'):
            self._link_printing_design_to_quotation()
        return res

    def _reprice_printing_lines(self):
        """Recalcula el precio de las líneas de estampado tras cambiar el diseño."""
        # Incluye las cotizaciones/pedidos en espera de validación: la ficha de
        # estampado suele cerrarse mientras la cotización ya está pendiente.
        for line in self.filtered(lambda l: l.is_weaving and l.bom_id
                                  and l.state in ('draft', 'sent', 'sale', 'pending_admin_approval', 'pending_finance_approval')):
            try:
                new_price = line.with_context(
                    skip_printing_reprice=True).get_weaving_price_unit()
            except Exception as e:  # noqa: BLE001 - no debe bloquear el guardado
                _logger.warning('No se pudo recalcular el precio de %s: %s', line.id, e)
                continue
            if not new_price:
                continue
            rounding = line.currency_id.rounding or 0.01
            if float_compare(new_price, line.price_unit, precision_rounding=rounding) != 0:
                line.with_context(skip_printing_reprice=True).write({
                    'price_unit': new_price,
                    'technical_price_unit': new_price,
                })
    
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