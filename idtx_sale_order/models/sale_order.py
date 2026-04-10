from odoo import models, fields, Command, api, _
from odoo.exceptions import UserError
from odoo.tools import html_escape
from markupsafe import Markup
import json

class SaleOrder(models.Model):
    _inherit = 'sale.order'
    
    lab_dev_ids = fields.Many2many('lab.dev', string='Lab Dev', copy=False, tracking=True)
    weaving_warning = fields.Text('weaving_warning', compute='_compute_weaving_warning')
    dieying_info = fields.Text('dieying_info', compute='_compute_dieying_info')
    sale_order_ids = fields.One2many('sale.order', 'quotation_id', string='Sale Orders')
    quotation_id = fields.Many2one('sale.order', string='Quotation')
    applicant_id = fields.Many2one('res.partner', string='Applicant')
    sale_type = fields.Selection([
        ('sale', 'Sale'),
        ('service', 'Service'),
        # ('sample', 'Sample'),
        # ('pilot', 'Pilot'),
    ], string='Sale Type', default='sale')
    production_count = fields.Integer('Production Count', compute='_compute_production_count')
    sale_count = fields.Integer('Sales Count', compute='_compute_sale_count')
    is_quote = fields.Boolean('is_quote', default=True)
    # is_manual_lab_dev = fields.Boolean('is_manual_lab_dev', default=False)
    lab_dev_count = fields.Integer(string="Technical Sheet Count", compute='_compute_lab_dev_count')
    is_company_produce = fields.Boolean(related='company_id.is_company_produce')
    need_labdev = fields.Boolean('Need LabDev?', compute='_compute_need_labdev', default=False)
    has_pending_labdev_lines = fields.Boolean('Has Pending LabDev Lines', compute='_compute_need_labdev', default=False)
    color_name_warning = fields.Boolean(default=False)
    need_approval = fields.Boolean('need_approval?', compute='_compute_need_approval')
    state = fields.Selection(selection_add=[('for_app', 'For Approval')])
    is_printing = fields.Boolean(compute='_compute_is_printing')
    is_rotary = fields.Boolean(compute='_compute_is_rotary')
    is_digital = fields.Boolean(compute='_compute_is_digital')

    @api.depends('order_line.is_printing')
    def _compute_is_printing(self):
        for rec in self:
            rec.is_printing = bool(any(l.is_printing for l in rec.order_line))

    @api.depends('order_line.is_printing')
    def _compute_is_rotary(self):
        for rec in self:
            rec.is_rotary = bool(any(l.printing_design_id.printing_type == 'rotary' for l in rec.order_line))

    @api.depends('order_line.is_printing')
    def _compute_is_digital(self):
        for rec in self:
            rec.is_digital = bool(any(l.printing_design_id.printing_type == 'digital' for l in rec.order_line))

    @api.depends('order_line.dis_app')
    def _compute_need_approval(self):
        for rec in self:
            if any(not line.dis_app for line in rec.order_line):
                rec.need_approval = True
            else:
                rec.need_approval = False

    def action_request_approval(self):
        self.state = 'for_app'

    def action_approve(self):
        self.order_line.dis_app = True
        self.state = 'draft'

    def action_quotation_send(self):
        if self.need_approval:
            raise UserError(_('Can\'t send quotation without approval for discount.'))
        if self.weaving_warning:
            raise UserError(_('Please solve all the warnings first.'))
        action = super().action_quotation_send()
        if len(self) != 1:
            return action
        sheets = self.order_line.mapped('bom_id.technical_sheet_id').filtered(lambda s: s)
        if sheets:
            ctx = dict(action.get('context', {}))
            ctx['technical_sheet_ids_to_attach'] = sheets.ids
            action['context'] = ctx
        return action
    
    def write(self, vals):
        res = super().write(vals)
        if not self.env.context.get('skip_original_labdev_guard') and ('lab_dev_ids' in vals or 'order_line' in vals):
            self._ensure_original_lab_devs()
        if 'lab_dev_ids' in vals:
            self._cleanup_orphan_lab_dev_lines()
        return res

    def _ensure_original_lab_devs(self):
        for order in self:
            if not order.id:
                continue
            original_lab_devs = self.env['lab.dev'].search([('sale_order_id', '=', order.id)])
            missing = original_lab_devs - order.lab_dev_ids
            if missing:
                super(SaleOrder, order.with_context(skip_original_labdev_guard=True)).write({
                    'lab_dev_ids': [Command.link(lab.id) for lab in missing],
                })

    def _cleanup_orphan_lab_dev_lines(self):
        for order in self:
            orphan_lines = order.order_line.filtered(
                lambda l: l.lab_dev_line_id and l.lab_dev_line_id.lab_dev_id not in order.lab_dev_ids
            )
            if orphan_lines:
                orphan_lines.lab_dev_line_id = False
    
    def update_color_names(self):
        for l in self.order_line:
            prod = l.product_id.display_name
            before = l.color_name
            after = l.lab_dev_line_id.display_name
            body = Markup(_('Color changed in line <b>%s</b>: <br/> %s <i class="o-mail-Message-trackingSeparator fa fa-long-arrow-right mx-2 text-600"></i> <span class="text-info fw-bold">%s</span>') % (html_escape(prod), html_escape(before), html_escape(after)))
            self.message_post(body=body, message_type="comment", subtype_xmlid="mail.mt_note",)
            l.color_name = l.lab_dev_line_id.color_name
        self.color_name_warning = False

    @api.depends('order_line.product_template_id', 'order_line.product_template_id.is_weaving', 'order_line.product_color_id', 'order_line.product_color_id.is_lab_color', 'order_line.lab_dev_line_id')
    def _compute_need_labdev(self):
        for rec in self:
            target_lines = rec.order_line.filtered(
                lambda l: l.product_template_id.is_weaving and l.product_color_id.is_lab_color
            )
            rec.need_labdev = bool(target_lines)
            rec.has_pending_labdev_lines = any(not line.lab_dev_line_id for line in target_lines)

    @api.depends('lab_dev_ids')
    def _compute_lab_dev_count(self):
        for rec in self:
            rec.lab_dev_count = len(rec.lab_dev_ids)

    @api.depends('order_line.production_id')
    def _compute_production_count(self):
        for rec in self:
            rec.production_count = len(rec.order_line.production_id)

    @api.depends('sale_order_ids')
    def _compute_sale_count(self):
        for rec in self:
            rec.sale_count = len(rec.sale_order_ids)

    @api.onchange('sale_type')
    def _onchange_sale_type(self):
        for rec in self:
            rec.order_line._onchange_bom_id()
            rec.order_line._onchange_product_or_color()

    @api.onchange('payment_term_id','incoterm')
    def _onchange_payment_term_id(self):
        self.order_line._compute_price_unit()

    @api.onchange('order_line')
    def _onchange_order_line_lab_dev_line_id(self):
        for order in self:
            # Mantener siempre los LD creados desde esta orden,
            # aunque temporalmente no aparezcan en las lineas.
            original_lab_devs = self.env['lab.dev']
            if order.id:
                original_lab_devs = self.env['lab.dev'].search([('sale_order_id', '=', order.id)])
            line_lab_devs = order.order_line.mapped('lab_dev_line_id.lab_dev_id')
            # Recalcular desde fuentes reales para permitir quitar LD agregadas manualmente
            # que ya no esten vinculadas a lineas.
            order.lab_dev_ids = original_lab_devs | line_lab_devs

    @api.onchange('lab_dev_ids')
    def _onchange_lab_dev_ids(self):
        for order in self:
            current_ids = set(order.lab_dev_ids.ids)
            for line in order.order_line:
                if not line.lab_dev_line_id:
                    continue
                # No borrar vinculacion si la linea pertenece a un LD original de la orden.
                if line.lab_dev_line_id.lab_dev_id.sale_order_id == order:
                    continue
                if line.lab_dev_line_id.lab_dev_id.id not in current_ids:
                    line.lab_dev_line_id = False

    def create_labdev(self):
        if any(not line.color_name for line in self.order_line.filtered(lambda l: l.product_template_id.is_weaving and l.product_color_id.is_lab_color)):
            raise UserError(_('Can\'t create Lab Dev some lines have no color name.'))
        today = fields.Date.context_today(self)
        data = {
            'lab_dev_date': today,
            'sale_order_id': self.id,
            'partner_id': self.partner_id.id,
            'lab_dev_line_ids': [Command.create({
                #  'product_id': line.product_template_id.id,
                 'color_name': line.color_name or line.product_color_id.name,
                 'sale_order_line_id': line.id,
            }) for line in self.order_line.filtered(lambda l: l.product_template_id.is_weaving and l.product_color_id.is_lab_color and not l.lab_dev_line_id)]
        }
        lab_dev = self.env['lab.dev'].create(data)
        self.lab_dev_ids = self.lab_dev_ids | lab_dev
        for ld_line in lab_dev.lab_dev_line_ids:
            if ld_line.sale_order_line_id:
                ld_line.sale_order_line_id.lab_dev_line_id = ld_line.id
        self.open_labdev()
    
    def open_labdev(self):
        return self.lab_dev_ids._get_records_action(name=_("Lab Dev"))
    
    def open_productions(self):
        return self.order_line.production_id._get_records_action(name=_("Productions"))
    
    def open_sales(self):
        return self.sale_order_ids._get_records_action(name=_("Sale Orders"))
    
    def refresh_warnings(self):
        for rec in self:
            for line in rec.order_line:
                line._compute_price_unit()
    
    @api.depends('order_line','partner_id','pricelist_id')
    def _compute_weaving_warning(self):
        for order in self:
            if order.weaving_warning:
                has_warning = True
            else:
                has_warning = False
            order.weaving_warning = ''
            if order.partner_id and not order.pricelist_id:
                order.weaving_warning += _(('This sale order has no price list or the option is not activated.')) + '\n'
            else:
                for line in order.order_line.filtered(lambda l: l.product_template_id.is_weaving):
                    # if line.product_template_id.bom_ids:
                    if line.bom_id:
                        bom_id = line.bom_id
                        bom_lines = bom_id.bom_line_ids
                    else:
                        bom_id = line.analysis_id.weaving_data_ids[0] if line.analysis_id.weaving_data_ids else self.env['analysis.weaving.data']
                        bom_lines = bom_id.mapped('fiber_ids')
                    for bom_line in bom_lines:
                        if line.bom_id:
                            product = bom_line.product_id
                            quantity = bom_line.product_qty or 0
                        else:
                            product = bom_line.product_template_id
                            quantity = bom_line.percentage or 0
                        pricelist_item_id = line.order_id.pricelist_id._get_product_rule(
                            product,
                            quantity=quantity or 1.0,
                            uom=product.uom_id,
                            date=line._get_order_date(),
                        )
                        item = self.env['product.pricelist.item'].browse(pricelist_item_id)
                        price = item.fixed_price if pricelist_item_id else 0
                        if not pricelist_item_id and order.partner_id or not price:
                            order.weaving_warning += _(('Product %s has product %s on its bom and does not have a price in %s price list. The price is obtained from its own sale price.') %( line.product_id.product_tmpl_id.display_name, bom_line.product_id.product_tmpl_id.display_name, order.pricelist_id.name)) + '\n'
                    if not bom_id:
                        operations = line.product_template_id.analysis_id.routing_ids.sorted(key=lambda r: r.sequence).filtered(lambda l: l.operation_id.unit_price > 0 or l.operation_id.type_prices == 'col' and sum(l.operation_id.product_color_price_ids.mapped('unit_price')) > 0 or l.operation_id.operation_type == 'weaving')
                    else:
                        operations = line.operation_ids.sorted(key=lambda r: r.sequence)
                    for operation in operations:
                    # for operation in bom_id.operation_ids:
                        if operation.operation_id.type_prices == 'col' and line.product_color_id.is_lab_color:
                            operation_color_line = operation.operation_id.product_color_price_ids.search([('product_color_id','=',line.product_color_id.id),('mrwo_id','=', operation.operation_id.id)])
                            if not operation_color_line:
                                order.weaving_warning += (_('The type prices of %s operation is by color. The color %s does not exists in the operation color list, product %s.') %(operation.operation_id.name, line.product_color_id.name, line.product_id.product_tmpl_id.display_name)) + '\n'
                # for line in order.order_line.filtered(lambda l: l.product_template_id.is_weaving):
                    if line.lab_dev_line_id and line.color_name:
                        if line.color_name.upper() != line.lab_dev_line_id.color_name.upper():
                            order.weaving_warning += (_('Product %s color %s does not match lab color name %s.') %(line.product_id.product_tmpl_id.display_name, line.color_name, line.lab_dev_line_id.color_name)) + '\n'
                            order.color_name_warning = True
                    else:
                        if not line.color_name:
                            line.color_name = line.lab_dev_line_id.color_name
                    if line.diff_days:                        
                        order.weaving_warning += _(('Product %s has an old price. Quotation is %s days old') %( line.product_id.product_tmpl_id.display_name, line.diff_days)) + '\n'
                    # if not line.product_template_id.bom_ids:
                    #     order.weaving_warning += _(('Product %s does not have any bom. Please check with product development.')  % line.product_id.product_tmpl_id.display_name) + '\n'
                    if not line.product_id.analysis_id.weaving_price:
                        order.weaving_warning += _(('Product %s has no weaving price. Please check with product development') % line.product_id.product_tmpl_id.display_name) + '\n'

                    has_weaving_operation = any(
                        operation.operation_id and operation.operation_id.operation_type == 'weaving'
                        for operation in operations
                    )
                    if has_weaving_operation and line.order_id.sale_type == 'sale' and self.is_quote:
                        try:
                            price_dict = json.loads(line.price_items or '{}')
                        except (json.JSONDecodeError, TypeError):
                            price_dict = {}

                        has_thread_items = any(
                            isinstance(item, dict) and item.get('is_thread')
                            for key, item in (price_dict or {}).items()
                            if not str(key).startswith('__')
                        )
                        if not has_thread_items:
                            order.weaving_warning += _(
                                'Product %s has weaving operation but no thread items were found in price details.'
                            ) % (line.product_id.product_tmpl_id.display_name,) + '\n'

            # Si se limpian los warnings, calculamos los precios nuevamente
            if has_warning and not order.weaving_warning:
                for l in order.order_line:
                    l._compute_price_unit()

    @api.depends('order_line')
    def _compute_dieying_info(self):
        # TODO cuando el ingeniero Yagui termine la información, se creará el sistema de alerta
        # que tambien servirá para la programación de partidas
        pass

    def action_price_preview(self):
        self.ensure_one()
        url = self.get_portal_url(suffix='/price_items')
        return {
            'type': 'ir.actions.act_url',
            'target': 'self',
            'url': url,
        }
    
    def _validate_order(self):
        # Evitamos confirmar la cotizacion al firmar desde el portal
        if self.is_quote:
            return
        return super()._validate_order()

    def action_confirm(self):
        for rec in self:
            if not rec.is_quote and not rec.lab_dev_ids and rec.company_id.is_company_produce and any(line.product_template_id.is_weaving and line.product_color_id.is_lab_color for line in self.order_line):
                raise UserError(_('Cant\'t confirm sale order without LD'))
            if rec.is_quote and rec.company_id.is_company_produce:
                raise UserError(_('Cant\'t confirm a quotation.'))
        res = super().action_confirm()
        for rec in self:
            for line in rec.order_line:
                if line.product_uom_qty and line.product_id.is_weaving and line.bom_id:
                    # Si es un servicio o se quitaron algunas operaciones guardamos la diferencia para quitarlas
                    # operations_to_delete = line.bom_id.operation_ids.operation_id - line.operation_ids.operation_id
                    prd = self.env['mrp.production'].create({
                        'product_tmpl_id': line.product_id.product_tmpl_id.id,
                        'product_qty': line.product_uom_qty,
                        'bom_id': line.bom_id.id,
                        'sale_order_line_id': line.id,
                        'sale_type': rec.sale_type,
                    })
                    # wo_to_delete = prd.workorder_ids.filtered(lambda wo: wo.mrwo_id in operations_to_delete)
                    # wo_to_delete.unlink()
                    line.production_id = prd
                    if prd.color_recipe_id:
                        prd.action_confirm()
                    prd.do_unreserve()
            if not rec.company_id.is_company_produce:
                rec.is_quote = False
        return res
    
    def action_create_sale_order(self):
        self.ensure_one()
        if any(not line.bom_id for line in self.order_line.filtered(lambda l: l.product_template_id.is_weaving)):
            raise UserError(_('All weaving lines must have a bill of materials to create a sale order.'))
        if self.is_quote and self.weaving_warning:
            raise UserError(_('Please solve all the warnings first.'))
        sale_order = self.copy({
                'quotation_id': self.id,
                'is_quote': False,
            })
        self.sale_order_ids = [Command.link(sale_order.id)]
        return self.sale_order_ids._get_records_action(name=_("Sale Orders"))
    
    def action_cancel(self):
        res = super().action_cancel()
        self.order_line.production_id.with_context(delete_from_sale_order=True).unlink() 
        return res
    
    @api.onchange('partner_id')
    def _onchange_partner_id(self):
        for rec in self:
            rec.applicant_id = False