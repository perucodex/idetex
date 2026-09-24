from odoo import _, api, fields, models

# Campos del diseño cuyo cambio altera el recargo de estampado de las líneas.
PRICE_FIELDS = ('unit_price', 'bonding_price', 'digital_unit_price_ids', 'rotary_unit_price_ids', 'printing_type')


class PrintingDesign(models.Model):
    _inherit = 'printing.design'

    # Última actualización del recargo de estampado de la ficha: cambio de un
    # campo de precio (PRICE_FIELDS) o paso a Hecho (momento en que el precio
    # vale para la cotización). La muestra el widget de fechas de precio de los
    # procesos del vendedor (JP, 23-sep-2026).
    price_date = fields.Datetime(
        'Fecha de precio', readonly=True, copy=False,
        help='Última actualización del precio de estampado de la ficha o su paso a Hecho.')

    @api.model_create_multi
    def create(self, vals_list):
        now = fields.Datetime.now()
        for vals in vals_list:
            if any(vals.get(f) for f in PRICE_FIELDS if f != 'printing_type'):
                vals.setdefault('price_date', now)
        return super().create(vals_list)

    def write(self, vals):
        if 'price_date' not in vals and (
                vals.get('state') == 'done' or any(f in vals for f in PRICE_FIELDS)):
            vals = dict(vals, price_date=fields.Datetime.now())
        res = super().write(vals)
        # La cotización se recalcula cuando la ficha pasa a Hecho y cuando, ya
        # hecha, desarrollo ajusta el precio (JP, 22-sep-2026).
        if vals.get('state') == 'done' or any(f in vals for f in PRICE_FIELDS):
            self.filtered(lambda d: d.state == 'done')._update_quotation_prices()
        return res

    def _update_quotation_prices(self):
        """Recalcula el recargo de estampado de las líneas de COTIZACIÓN vivas
        que usan estas fichas y lo anota en el chatter de la cotización. Corre
        con sudo porque quien cierra la ficha es desarrollo, sin permisos sobre
        las cotizaciones de ventas."""
        for design in self:
            lines = design.sudo().sale_line_ids.filtered(
                lambda l: l.order_id.is_quote and not l.order_id.locked
                and l.order_id.state in ('draft', 'sent', 'pending_admin_approval'))
            if not lines:
                continue
            before = {line.id: line.price_unit for line in lines}
            lines.with_context(force_printing_reprice=True)._reprice_printing_lines()
            lines.invalidate_recordset(['price_unit'])
            for order in lines.order_id:
                changed = lines.filtered(lambda l: l.order_id == order and l.price_unit != before[l.id])
                if changed:
                    order.message_post(
                        body=_('Precio de estampado actualizado desde la ficha %s (Hecho): %s.',
                               design.display_name,
                               ', '.join('%s → %s' % (l.product_template_id.name, l.price_unit) for l in changed)),
                        message_type='comment', subtype_xmlid='mail.mt_note')

    # Cotización desde la que el vendedor creó la ficha (JP, 22-sep-2026). Se
    # enlaza al guardar la línea que usa el diseño (o desde el botón de la
    # cotización). Solo trazabilidad: no restringe dónde se puede usar.
    quotation_id = fields.Many2one(
        'sale.order', string='Cotización de origen', copy=False, index=True,
        ondelete='set null', domain="[('is_quote', '=', True)]")
    sale_line_ids = fields.One2many('sale.order.line', 'printing_design_id', string='Líneas de venta')
    # Vendedor que creó la ficha (quien la abrió desde la cotización). Se fija
    # en create() y no cambia; para las fichas antiguas queda vacío salvo las
    # que ya tenían cotización de origen (migración 19.0.0.16.1). Sin `default`
    # a propósito: al crear la columna, Odoo rellena las filas existentes con
    # el default y todas quedaban con OdooBot.
    salesperson_id = fields.Many2one(
        'res.users', string='Vendedor', readonly=True, copy=False, index=True, ondelete='set null')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            vals.setdefault('salesperson_id', self.env.uid)
        return super().create(vals_list)

    @api.model
    def default_get(self, fields_list):
        """Ficha creada desde una línea de cotización: precarga tela, ancho,
        densidad y rendimiento del análisis del producto cotizado para que el
        vendedor no los copie a mano (contexto quote_product_tmpl_id)."""
        res = super().default_get(fields_list)
        tmpl_id = self.env.context.get('quote_product_tmpl_id')
        if tmpl_id:
            tmpl = self.env['product.template'].browse(tmpl_id).exists()
            analysis = tmpl.analysis_id if tmpl else self.env['product.analysis']
            defaults = {
                'fabric_base': tmpl.name,
                'width': analysis.standard_width,
                'density': analysis.density,
                'yield_meter': analysis.yield_meter,
            }
            for name, value in defaults.items():
                if name in fields_list and not res.get(name) and value:
                    res[name] = value
        return res


class PrintingDesignPrice(models.Model):
    _inherit = 'printing.design.price'

    def write(self, vals):
        res = super().write(vals)
        # Precio de un rango digital cambiado con la ficha ya Hecha: la
        # cotización se recalcula igual que al cambiar el precio rotativo.
        if 'unit_price' in vals:
            designs = (self.mapped('digital_printing_id') | self.mapped('rotary_printing_id')).filtered(lambda d: d.state == 'done')
            designs._update_quotation_prices()
        return res
