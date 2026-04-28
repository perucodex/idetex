from odoo import models, fields, Command, api, _
from odoo.exceptions import UserError, AccessError
from odoo.tools import html_escape
from markupsafe import Markup
import json

class SaleOrder(models.Model):
    _inherit = 'sale.order'
    
    lab_dev_ids = fields.Many2many('lab.dev', string='Lab Dev', tracking=True)
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
    production_ids = fields.Many2many('mrp.production', string='Production')
    production_count = fields.Integer(string="Production Count", compute='_compute_production_count')
    sale_count = fields.Integer('Sales Count', compute='_compute_sale_count')
    is_quote = fields.Boolean('is_quote', default=True)
    # is_manual_lab_dev = fields.Boolean('is_manual_lab_dev', default=False)
    lab_dev_count = fields.Integer(string="Technical Sheet Count", compute='_compute_lab_dev_count')
    has_order_lab_dev = fields.Boolean('Has Order LabDev', compute='_compute_has_order_lab_dev')
    is_company_produce = fields.Boolean(related='company_id.is_company_produce')
    need_labdev = fields.Boolean('Need LabDev?', compute='_compute_need_labdev', default=False)
    has_pending_labdev_lines = fields.Boolean('Has Pending LabDev Lines', compute='_compute_need_labdev', default=False)
    sale_approval_required = fields.Boolean('Sale Approval Required', compute='_compute_sale_approval_required')
    color_name_warning = fields.Boolean(default=False)
    need_approval = fields.Boolean('need_approval?', compute='_compute_need_approval')
    state = fields.Selection(
        selection_add=[
            ('for_app', 'For Approval'),
            ('pending_admin_approval', 'Pending Administrative Approval'),
            ('pending_finance_approval', 'Pending Financial Approval'),
            ('sale',),
        ],
        ondelete={
            'for_app': 'set default',
            'pending_admin_approval': 'set default',
            'pending_finance_approval': 'set default',
        },
    )
    admin_approval_user_id = fields.Many2one('res.users', string='Administrative Approved By', copy=False, readonly=True)
    admin_approval_date = fields.Datetime(string='Administrative Approval Date', copy=False, readonly=True)
    finance_approval_user_id = fields.Many2one('res.users', string='Financial Approved By', copy=False, readonly=True)
    finance_approval_date = fields.Datetime(string='Financial Approval Date', copy=False, readonly=True)
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

    @api.depends('is_company_produce', 'is_quote', 'order_line.product_template_id', 'order_line.product_template_id.is_weaving')
    def _compute_sale_approval_required(self):
        for rec in self:
            rec.sale_approval_required = rec._requires_sale_approval_workflow()

    def action_request_approval(self):
        self.state = 'for_app'

    def action_approve(self):
        self.order_line.dis_app = True
        self.state = 'draft'

    def action_request_sale_approval(self):
        orders = self.filtered(lambda order: order._requires_sale_approval_workflow())
        orders._validate_sale_confirmation_requirements()
        orders.write({
            'state': 'pending_admin_approval',
            'admin_approval_user_id': False,
            'admin_approval_date': False,
            'finance_approval_user_id': False,
            'finance_approval_date': False,
        })
        return True

    def action_admin_approve(self):
        if not self.env.user.has_group('idtx_sale_order.group_sale_order_admin_approver'):
            raise AccessError(_('You do not have permission to approve sales orders at the administrative level.'))
        pending_orders = self.filtered(lambda order: order.state == 'pending_admin_approval' and not order.is_quote and order._requires_sale_approval_workflow())
        pending_orders.write({
            'state': 'pending_finance_approval',
            'admin_approval_user_id': self.env.user.id,
            'admin_approval_date': fields.Datetime.now(),
        })
        return True

    def action_finance_approve(self):
        if not self.env.user.has_group('idtx_sale_order.group_sale_order_finance_approver'):
            raise AccessError(_('You do not have permission to approve sales orders at the financial level.'))
        pending_orders = self.filtered(lambda order: order.state == 'pending_finance_approval' and not order.is_quote and order._requires_sale_approval_workflow())
        pending_orders.write({
            'finance_approval_user_id': self.env.user.id,
            'finance_approval_date': fields.Datetime.now(),
        })
        return pending_orders._run_sale_confirmation()

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

    def _get_pricing_pricelist(self):
        self.ensure_one()
        return self.company_id.sales_pricelist_id or self.pricelist_id

    def _requires_sale_approval_workflow(self):
        self.ensure_one()
        return bool(
            not self.is_quote
            and self.is_company_produce
            and any(line.product_template_id.is_weaving for line in self.order_line)
        )

    def _confirmation_error_message(self):
        self.ensure_one()
        if self._requires_sale_approval_workflow() and self.state == 'pending_finance_approval':
            if any(
                not line.display_type
                and not line.is_downpayment
                and not line.product_id
                for line in self.order_line
            ):
                return _('Some order lines are missing a product, you need to correct them before going further.')
            return False
        return super()._confirmation_error_message()

    def _validate_sale_confirmation_requirements(self):
        for rec in self:
            if not rec.is_quote and not rec.lab_dev_ids and rec.company_id.is_company_produce and any(line.product_template_id.is_weaving and line.is_lab_color for line in rec.order_line):
                raise UserError(_('Cant\'t confirm sale order without LD'))
            lines = rec.order_line.filtered(lambda line: line.product_template_id.is_weaving and line.is_lab_color)
            if any(not line.lab_dev_line_id for line in lines):
                raise UserError(_('Cant\'t confirm sale order without colors.'))
            if rec.is_quote and rec.company_id.is_company_produce:
                raise UserError(_('Cant\'t confirm a quotation.'))

    def _subscribe_sale_approval_followers(self):
        orders = self.filtered(lambda order: not order.is_quote and order.is_company_produce)
        if not orders:
            return

        admin_group = self.env.ref('idtx_sale_order.group_sale_order_admin_approver', raise_if_not_found=False)
        finance_group = self.env.ref('idtx_sale_order.group_sale_order_finance_approver', raise_if_not_found=False)
        approver_users = (admin_group.all_user_ids | finance_group.all_user_ids).filtered(
            lambda user: user.active and user.partner_id
        )
        partner_ids = approver_users.mapped('partner_id').ids
        if partner_ids:
            orders.sudo().message_subscribe(partner_ids=partner_ids)

    def _run_sale_confirmation(self):
        self._validate_sale_confirmation_requirements()
        res = super(SaleOrder, self).action_confirm()
        for rec in self:
            for line in rec.order_line:
                if line.product_uom_qty and line.product_id.is_weaving and line.bom_id:
                    # production_state = line.bom_id.technical_sheet_id.production_state
                    production_env = self.env['mrp.production'].sudo().with_company(rec.company_id)
                    prd = production_env.create({
                        'product_tmpl_id': line.product_id.product_tmpl_id.id,
                        'product_qty': line.product_uom_qty,
                        'bom_id': line.bom_id.id,
                        'sale_order_line_id': line.id,
                        'sale_type': rec.sale_type,
                    })
                    line.sudo().production_id = prd.id
                    self.production_ids = [(4, prd.id)]
                    # if prd.color_recipe_id and production_state and production_state != 'Sample':
                    if prd.color_recipe_id:
                        prd.action_confirm()
                    prd.do_unreserve()
            if not rec.company_id.is_company_produce:
                rec.is_quote = False
        return res

    def _recompute_order_line_prices_from_terms(self):
        for order in self:
            weaving_lines = order.order_line.filtered(
                lambda line: line.company_id.is_company_produce and line.product_id.is_weaving
            )
            if weaving_lines:
                weaving_lines._compute_price_unit()

    @api.model_create_multi
    def create(self, vals_list):
        orders = super().create(vals_list)
        orders.filtered(lambda order: not order.is_quote and order.quotation_id)._recompute_order_line_prices_from_terms()
        return orders
    
    def write(self, vals):
        res = super().write(vals)
        if not self.env.context.get('skip_original_labdev_guard') and ('lab_dev_ids' in vals or 'order_line' in vals):
            self._ensure_original_lab_devs()
        if 'lab_dev_ids' in vals:
            self._cleanup_orphan_lab_dev_lines()
        if 'payment_term_id' in vals or 'incoterm' in vals:
            self._recompute_order_line_prices_from_terms()
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
        for l in self.order_line.filtered(lambda l: l.lab_dev_line_id):
            prod = l.product_id.display_name
            before = l.color_name
            after = l.lab_dev_line_id.display_name
            body = Markup(_('Color changed in line <b>%s</b>: <br/> %s <i class="o-mail-Message-trackingSeparator fa fa-long-arrow-right mx-2 text-600"></i> <span class="text-info fw-bold">%s</span>') % (html_escape(prod), html_escape(before), html_escape(after)))
            self.message_post(body=body, message_type="comment", subtype_xmlid="mail.mt_note",)
            l.color_name = l.lab_dev_line_id.color_name
        self.color_name_warning = False

    @api.depends('order_line.product_template_id', 'order_line.product_template_id.is_weaving', 'order_line.is_lab_color', 'order_line.lab_dev_line_id')
    def _compute_need_labdev(self):
        for rec in self:
            target_lines = rec.order_line.filtered(
                lambda l: l.product_template_id.is_weaving and l.is_lab_color
            )
            rec.need_labdev = bool(target_lines)
            rec.has_pending_labdev_lines = any(not line.lab_dev_line_id for line in target_lines)

    @api.depends('lab_dev_ids', 'lab_dev_ids.sale_order_id')
    def _compute_has_order_lab_dev(self):
        for rec in self:
            rec.has_order_lab_dev = bool(rec.id and rec.lab_dev_ids.filtered(lambda lab_dev: lab_dev.sale_order_id.id == rec.id))

    @api.depends('lab_dev_ids')
    def _compute_lab_dev_count(self):
        for rec in self:
            rec.lab_dev_count = len(rec.lab_dev_ids)

    @api.depends('production_ids')
    def _compute_production_count(self):
        for rec in self:
            rec.production_count = len(rec.production_ids)

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
        self._recompute_order_line_prices_from_terms()

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
        if any(not line.color_name for line in self.order_line.filtered(lambda l: l.product_template_id.is_weaving and l.is_lab_color)):
            raise UserError(_('Can\'t create Lab Dev some lines have no color name.'))
        today = fields.Date.context_today(self)
        data = {
            'lab_dev_date': today,
            'sale_order_id': self.id,
            'partner_id': self.partner_id.id,
            'lab_dev_line_ids': [Command.create({
                #  'product_id': line.product_template_id.id,
                 'color_name': color.upper(),
                #  'sale_order_line_id': line.id,
            }) for color in set(self.order_line.filtered(lambda l: l.product_template_id.is_weaving and l.is_lab_color and not l.lab_dev_line_id).mapped('color_name'))]
        }
        lab_dev = self.env['lab.dev'].create(data)
        self.lab_dev_ids = self.lab_dev_ids | lab_dev
        # for ld_line in lab_dev.lab_dev_line_ids:
        #     if ld_line.sale_order_line_id:
        #         ld_line.sale_order_line_id.lab_dev_line_id = ld_line.id
        for line in self.order_line.filtered(lambda l: l.product_template_id.is_weaving and l.is_lab_color and not l.lab_dev_line_id):
            line.color_name = line.color_name.upper()
            line.lab_dev_line_id = lab_dev.lab_dev_line_ids.filtered(lambda l: l.color_name == line.color_name)
        self.open_labdev()
    
    def open_labdev(self):
        return self.lab_dev_ids._get_records_action(name=_("Lab Dev"))
    
    def open_productions(self):
        productions = self.production_ids
        if self.env.user.has_group('idtx_sale_order.group_sale_mrp_readonly') and not self.env.user.has_group('mrp.group_mrp_user'):
            return productions.with_context(create=False, edit=False, delete=False)._get_records_action(name=_("Productions"))
        return productions._get_records_action(name=_("Productions"))
    
    def open_sales(self):
        return self.sale_order_ids._get_records_action(name=_("Sale Orders"))
    
    def refresh_warnings(self):
        for rec in self:
            for line in rec.order_line:
                line._compute_price_unit()
    
    @api.depends('order_line','partner_id','pricelist_id')
    def _compute_weaving_warning(self):
        for order in self:
            pricing_pricelist = order._get_pricing_pricelist()
            if order.weaving_warning:
                has_warning = True
            else:
                has_warning = False
            order.weaving_warning = ''
            if order.partner_id and not pricing_pricelist:
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
                        pricelist_item_id = pricing_pricelist._get_product_rule(
                            product,
                            quantity=quantity or 1.0,
                            uom=product.uom_id,
                            date=line._get_order_date(),
                        )
                        item = self.env['product.pricelist.item'].browse(pricelist_item_id)
                        price = item.fixed_price if pricelist_item_id else 0
                        if not pricelist_item_id and order.partner_id or not price and line.has_weaving_operation:
                            order.weaving_warning += _(('Product %s has product %s on its bom and does not have a price in %s price list. The price is obtained from its own sale price.') %( line.product_id.product_tmpl_id.display_name, product.display_name, pricing_pricelist.name)) + '\n'
                    if not bom_id:
                        operations = line.product_template_id.analysis_id.routing_ids.sorted(key=lambda r: r.sequence).filtered(lambda l: l.operation_id.unit_price > 0 or l.operation_id.type_prices == 'col' and sum(l.operation_id.product_color_price_ids.mapped('unit_price')) > 0 or l.operation_id.operation_type == 'weaving')
                    else:
                        operations = line.operation_ids.sorted(key=lambda r: r.sequence)
                    for operation in operations:
                    # for operation in bom_id.operation_ids:
                        if operation.operation_id.type_prices == 'col' and line.is_lab_color:
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
                        if not has_thread_items and price_dict:
                            order.weaving_warning += _(
                                'Product %s has weaving operation but no thread items were found in price details.'
                            ) % (line.product_id.product_tmpl_id.display_name,) + '\n'
                    if line.is_lab_color and not any(op.gives_color for op in line.operation_ids.mapped('operation_id')):
                        order.weaving_warning += _(('Product %s has a lab color %s but not operation to dieying.') %(line.product_id.product_tmpl_id.display_name, line.product_color_id.name)) + '\n'

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
        quote_orders = self.filtered(lambda order: order.is_quote)
        if quote_orders:
            return quote_orders._run_sale_confirmation()

        self.filtered(lambda order: not order.is_quote and order.is_company_produce and order.state not in ('sale', 'cancel'))._subscribe_sale_approval_followers()

        finance_orders = self.filtered(lambda order: order.state == 'pending_finance_approval' and order._requires_sale_approval_workflow())
        if finance_orders:
            return finance_orders._run_sale_confirmation()

        regular_orders = self.filtered(lambda order: not order._requires_sale_approval_workflow())
        if regular_orders:
            return super(SaleOrder, regular_orders).action_confirm()

        orders_to_submit = self.filtered(lambda order: order._requires_sale_approval_workflow() and order.state not in ('sale', 'cancel', 'pending_admin_approval', 'pending_finance_approval'))
        if orders_to_submit:
            return orders_to_submit.action_request_sale_approval()
        return True
    
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
        self.action_lock()
        sale_order._recompute_order_line_prices_from_terms()
        self.sale_order_ids = [Command.link(sale_order.id)]
        return self.sale_order_ids._get_records_action(name=_("Sale Orders"))
    
    def action_cancel(self):
        res = super().action_cancel()
        # self.order_line.production_id.with_context(delete_from_sale_order=True).unlink() 
        for production in self.production_ids.filtered(lambda p: p.state != 'cancel'):
            if production.state not in ('draft','confirmed'):
                state_label = dict(production._fields['state'].selection).get(production.state, production.state)
                raise UserError(_('Can\'t cancel production in %s') %state_label)
            production.action_cancel()
        for labdev in self.lab_dev_ids.filtered(lambda ld: ld.sale_order_id == self):
            if labdev.state not in ('draft', 'cancel'):
                state_label = dict(labdev._fields['state'].selection).get(labdev.state, labdev.state)
                raise UserError(_('Can\'t cancel lab dev in %s') % state_label)
            labdev.action_cancel()
            for line in self.order_line.filtered(lambda l: l.lab_dev_line_id and l.lab_dev_line_id.lab_dev_id == labdev):
                line.lab_dev_line_id = False
        return res
    
    @api.onchange('partner_id')
    def _onchange_partner_id(self):
        for rec in self:
            rec.applicant_id = False