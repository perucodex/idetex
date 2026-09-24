from odoo import models, fields, api, _
from odoo.fields import Command
from odoo.exceptions import UserError, AccessError
from odoo.tools import html_escape
from markupsafe import Markup
import json

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def _idtx_remove_core_sale_menus(self):
        """Elimina (si aún existen) los menús core de Cotizaciones/Órdenes
        que este módulo reemplaza. Llamado por data en cada instalación/
        upgrade; idempotente — un <delete> directo borra el xmlid junto con
        el menú y en los -u siguientes truena con "External ID not found"."""
        for xmlid in ('sale.menu_sale_quotations', 'sale.menu_sale_order'):
            menu = self.env.ref(xmlid, raise_if_not_found=False)
            if menu:
                menu.unlink()

    lab_dev_ids = fields.Many2many('lab.dev', string='Lab Dip', tracking=True)
    weaving_warning = fields.Text('weaving_warning', compute='_compute_weaving_warning')
    dieying_info = fields.Text('dieying_info', compute='_compute_dieying_info')
    sale_order_ids = fields.One2many('sale.order', 'quotation_id', string='Sale Orders')
    quotation_id = fields.Many2one('sale.order', string='Quotation')
    applicant_id = fields.Many2one('res.partner', string='Applicant')
    # Datos comerciales de la OC del cliente (pestaña Otra información > Ventas).
    client_order_date = fields.Date('Fecha de OC del cliente', tracking=True)
    sub_partner_id = fields.Many2one('res.partner', string='Sub-cliente', tracking=True)
    # Maestro SITPRO vtas_tipoorden, solo referencia (sin integración).
    process_type_id = fields.Many2one('sitpro.sale.type', string='Tipo de proceso', tracking=True)
    sale_type = fields.Selection([
        ('sale', 'Sale'),
        ('service', 'Service'),
        # ('sample', 'Sample'),
        # ('pilot', 'Pilot'),
    ], string='Sale Type', default='sale', required=True)
    production_ids = fields.Many2many('mrp.production', string='Production')
    production_count = fields.Integer(string="Production Count", compute='_compute_production_count')
    sale_count = fields.Integer('Sales Count', compute='_compute_sale_count')
    is_quote = fields.Boolean('is_quote', default=True)
    # Muestra (JP, 23-sep-2026): toggle en Otra información > Ventas. Al
    # activarlo el precio unitario de las líneas de tejido suma el recargo de
    # muestra (precio muestra / precio muestra estampado) del cliente o, si el
    # cliente no lo tiene, el de Ajustes > Ventas. Ver
    # sale.order.line._get_sample_surcharge. Se hereda al pasar a pedido (copy).
    is_sample = fields.Boolean(
        'Muestra', default=False, tracking=True,
        help='Cotización o pedido de muestra: el precio unitario de las líneas de tejido '
             'suma el precio de muestra (o de muestra estampado) del cliente; si el '
             'cliente no lo tiene configurado, el de Ajustes > Ventas.')
    # is_manual_lab_dev = fields.Boolean('is_manual_lab_dev', default=False)
    lab_dev_count = fields.Integer(string="Technical Sheet Count", compute='_compute_lab_dev_count')
    has_order_lab_dev = fields.Boolean('Has Order LabDip', compute='_compute_has_order_lab_dev')
    is_company_produce = fields.Boolean(related='company_id.is_company_produce')
    has_weaving_line = fields.Boolean('Has Weaving Line', compute='_compute_has_weaving_line')
    need_labdev = fields.Boolean('Need LabDip?', compute='_compute_need_labdev', default=False)
    has_pending_labdev_lines = fields.Boolean('Has Pending LabDip Lines', compute='_compute_need_labdev', default=False)
    sale_approval_required = fields.Boolean('Sale Approval Required', compute='_compute_sale_approval_required')
    quote_approval_required = fields.Boolean('Quotation Approval Required', compute='_compute_sale_approval_required')
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
    # Fichas de estampado de la cotización: las enlazadas en líneas más las
    # creadas desde el botón de la cotización (JP, 22-sep-2026).
    printing_design_ids = fields.Many2many('printing.design', compute='_compute_printing_design_ids', string='Fichas de estampado')
    printing_design_count = fields.Integer(compute='_compute_printing_design_ids')
    is_rotary = fields.Boolean(compute='_compute_is_rotary')
    is_digital = fields.Boolean(compute='_compute_is_digital')
    # Ordenes no cerradas
    unclosed = fields.Boolean('Unclosed', compute='_compute_unclosed', store=True)
    # Hilos cotizados (JP, 21-sep-2026): badge "N Hilos cotizados" en la
    # cabecera (widget thread_price_badge) que al hacer clic muestra, por hilo,
    # código, nombre y fecha de última actualización de su regla en la lista
    # de precios (JSON en thread_price_info). thread_price_date = la más
    # reciente (no se muestra en la vista; queda para listas/reportes).
    thread_price_count = fields.Integer(
        'Hilos cotizados', compute='_compute_thread_price_info',
        help='Hilos que intervienen en las líneas de tejido de la cotización. '
             'Clic para ver la fecha de precio de cada uno en la lista de precios.')
    thread_price_date = fields.Date(
        'Fecha de precios hilado', compute='_compute_thread_price_info',
        help='Última actualización de las reglas de la lista de precios de los '
             'hilos que intervienen en las líneas de tejido.')
    thread_price_info = fields.Text(compute='_compute_thread_price_info')

    def _get_thread_price_rows(self):
        """Hilos que intervienen en las líneas de tejido (componentes de hilado
        de la LdM o, sin LdM, fibras del análisis) con la regla de la lista de
        precios que usa la cotización y su fecha de última modificación.
        Lectura con sudo: ventas no necesita permisos de Fabricación."""
        self.ensure_one()
        order = self.sudo()
        pricelist = order._get_pricing_pricelist()
        if not pricelist:
            return []
        thread_categs = (order.company_id or self.env.company).thread_category_ids
        Item = self.env['product.pricelist.item'].sudo()
        rows, seen = [], set()
        for line in order.order_line.filtered(
                lambda l: not l.display_type and l.product_template_id.is_weaving):
            if line.bom_id:
                products = line.bom_id.bom_line_ids.filtered(
                    lambda b: b.product_tmpl_id.categ_id in thread_categs).mapped('product_id')
            else:
                products = line.product_template_id.analysis_id.weaving_data_ids.mapped(
                    'fiber_ids.product_template_id')
            for product in products:
                key = (product._name, product.id)
                if key in seen:
                    continue
                seen.add(key)
                item_id = pricelist._get_product_rule(
                    product, quantity=1.0, uom=product.uom_id, date=line._get_order_date())
                item = Item.browse(item_id) if item_id else Item
                write_date = item.write_date if item else False
                rows.append({
                    'code': product.default_code or '',
                    'name': product.name,
                    'date': fields.Datetime.to_string(write_date) if write_date else False,
                    'date_display': fields.Datetime.context_timestamp(
                        order, write_date).strftime('%d/%m/%Y %H:%M') if write_date
                    else _('Sin regla en la lista de precios'),
                    'has_rule': bool(item),
                })
        rows.sort(key=lambda r: (r['has_rule'], r['date'] or ''))
        return rows

    @api.depends('order_line.product_id', 'order_line.bom_id', 'order_line.display_type',
                 'pricelist_id', 'company_id', 'date_order')
    def _compute_thread_price_info(self):
        for order in self:
            rows = order._get_thread_price_rows()
            order.thread_price_count = len(rows)
            order.thread_price_info = json.dumps(rows)
            dates = [fields.Datetime.from_string(r['date']) for r in rows if r['date']]
            order.thread_price_date = fields.Date.context_today(
                order, timestamp=max(dates)) if dates else False

    @api.onchange('order_line')
    def _onchange_order_line_sync_complements(self):
        """Propaga color_name, product_color_id y lab_dev_line_id de la línea
        de producto inmediatamente anterior a los complementos que aún NO
        tienen valor propio (comodidad al agregarlos). Los complementos pueden
        elegir su propio color: los valores ya establecidos no se pisan.
        Debe vivir en el pedido (no en la línea), porque un onchange a nivel
        de línea no puede modificar líneas hermanas."""
        for order in self:
            previous = None
            for line in order.order_line:
                if line.display_type:
                    previous = None
                    continue
                if line.is_complement:
                    if previous is not None:
                        if previous.color_name and not line.color_name:
                            line.color_name = previous.color_name
                        if previous.product_color_id and not line.product_color_id:
                            line.product_color_id = previous.product_color_id
                        if previous.lab_dev_line_id and not line.lab_dev_line_id:
                            line.lab_dev_line_id = previous.lab_dev_line_id
                else:
                    previous = line

    @api.depends('order_line.qty_delivered', 'order_line.product_uom_qty')
    def _compute_unclosed(self):
        for rec in self:
            rec.unclosed = bool(any(line.qty_delivered < line.product_uom_qty for line in rec.order_line))

    # Evitar que salga las lineas debajo de la cotización con este mensaje:
    # "Conecta tu software con IDETEX S.A.C. para crear cotizaciones automaticas"
    def _get_edi_builders(self):
        return []
    
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

    @api.depends('is_company_produce', 'is_quote', 'order_line.product_template_id', 'order_line.product_template_id.is_weaving',
                 'company_id.quotation_admin_approval', 'company_id.sale_admin_approval', 'company_id.sale_finance_approval')
    def _compute_sale_approval_required(self):
        for rec in self:
            rec.sale_approval_required = rec._requires_sale_approval_workflow()
            rec.quote_approval_required = rec._requires_quote_approval()

    @api.depends('order_line.product_template_id', 'order_line.product_template_id.is_weaving')
    def _compute_has_weaving_line(self):
        for rec in self:
            rec.has_weaving_line = any(line.product_template_id.is_weaving for line in rec.order_line)

    def action_request_approval(self):
        self.state = 'for_app'

    def action_approve(self):
        self.order_line.dis_app = True
        self.state = 'draft'

    def action_request_sale_approval(self):
        orders = self.filtered(lambda order: order._requires_sale_approval_workflow())
        orders._validate_sale_confirmation_requirements()
        for order in orders:
            # Primer nivel activo según los interruptores de Ajustes > Ventas.
            first_state = 'pending_admin_approval' if order.company_id.sale_admin_approval else 'pending_finance_approval'
            order.write({
                'state': first_state,
                'admin_approval_user_id': False,
                'admin_approval_date': False,
                'finance_approval_user_id': False,
                'finance_approval_date': False,
            })
        return True

    @api.depends('order_line.printing_design_id')
    def _compute_printing_design_ids(self):
        Design = self.env['printing.design']
        by_quote = {}
        for design in Design.search([('quotation_id', 'in', self.ids)]) if self.ids else Design:
            by_quote.setdefault(design.quotation_id.id, Design)
            by_quote[design.quotation_id.id] |= design
        for rec in self:
            designs = rec.order_line.printing_design_id | by_quote.get(rec.id, Design)
            rec.printing_design_ids = designs
            rec.printing_design_count = len(designs)

    def action_new_printing_design(self):
        """Cotización: abre la ficha de cotización de estampado (formulario
        reducido del vendedor) ya enlazada a esta cotización y su cliente."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Ficha de cotización de estampado'),
            'res_model': 'printing.design',
            'view_mode': 'form',
            'views': [(self.env.ref('idtx_sale_order.view_printing_design_form_quote').id, 'form')],
            'target': 'new',
            'context': {
                'default_partner_id': self.partner_id.commercial_partner_id.id or self.partner_id.id,
                'default_quotation_id': self.id,
                'default_printing_date': fields.Date.context_today(self),
                'form_view_ref': 'idtx_sale_order.view_printing_design_form_quote',
            },
        }

    def action_view_printing_designs(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('idtx_sale_order.action_printing_design_from_quote')
        action['domain'] = [('id', 'in', self.printing_design_ids.ids)]
        action['context'] = dict(self.env.context, form_view_ref='idtx_sale_order.view_printing_design_form_quote',
                                 default_quotation_id=self.id, default_partner_id=self.partner_id.id)
        return action

    def action_request_quote_approval(self):
        """Cotización: pide la validación administrativa antes de enviarla al
        cliente (JP, 22-sep-2026). Solo nivel administrativo; la financiera
        es del pedido."""
        quotes = self.filtered(lambda order: order.is_quote and order.state == 'draft' and order._requires_quote_approval())
        for quote in quotes:
            if quote.need_approval:
                raise UserError(_('Primero resuelve la aprobación del descuento de la cotización %s.', quote.name))
            quote._check_printing_designs_priced()
            if quote.weaving_warning:
                raise UserError(_('Please solve all the warnings first.'))
        quotes.write({
            'state': 'pending_admin_approval',
            'admin_approval_user_id': False,
            'admin_approval_date': False,
        })
        quotes._subscribe_sale_approval_followers(levels=('admin',))
        return True

    def action_admin_approve(self):
        if not self.env.user.has_group('idtx_sale_order.group_sale_order_admin_approver'):
            raise AccessError(_('You do not have permission to approve sales orders at the administrative level.'))
        approval_vals = {
            'admin_approval_user_id': self.env.user.id,
            'admin_approval_date': fields.Datetime.now(),
        }
        # Cotizaciones: la aprobación las devuelve a borrador ya validadas;
        # el envío al cliente queda habilitado.
        pending_quotes = self.filtered(lambda order: order.state == 'pending_admin_approval' and order.is_quote)
        pending_quotes._check_printing_designs_priced()
        pending_quotes.write(dict(approval_vals, state='draft'))
        # Pedidos: pasan a validación financiera si está activa; si no, la
        # administrativa es la última y confirma el pedido (con bloqueo, como
        # hace la financiera).
        pending_orders = self.filtered(lambda order: order.state == 'pending_admin_approval' and not order.is_quote)
        to_finance = pending_orders.filtered(lambda order: order.company_id.sale_finance_approval)
        to_finance.write(dict(approval_vals, state='pending_finance_approval'))
        direct_orders = pending_orders - to_finance
        res = True
        if direct_orders:
            direct_orders.write(approval_vals)
            res = direct_orders._run_sale_confirmation()
            direct_orders.filtered(lambda o: o.state == 'sale').sudo().action_lock()
        return res

    def action_finance_approve(self):
        if not self.env.user.has_group('idtx_sale_order.group_sale_order_finance_approver'):
            raise AccessError(_('You do not have permission to approve sales orders at the financial level.'))
        pending_orders = self.filtered(lambda order: order.state == 'pending_finance_approval' and not order.is_quote)
        pending_orders.write({
            'finance_approval_user_id': self.env.user.id,
            'finance_approval_date': fields.Datetime.now(),
        })
        res = pending_orders._run_sale_confirmation()
        # Tras la aprobación financiera el pedido queda bloqueado: cualquier
        # cambio posterior exige desbloquearlo conscientemente.
        pending_orders.filtered(lambda o: o.state == 'sale').sudo().action_lock()
        return res

    def action_quotation_send(self):
        if self.need_approval:
            raise UserError(_('Can\'t send quotation without approval for discount.'))
        if self.weaving_warning:
            raise UserError(_('Please solve all the warnings first.'))
        self._check_quote_admin_approval()
        action = super().action_quotation_send()
        return action

    def _check_printing_designs_priced(self):
        """Cotización con fichas de estampado sin precio: no se solicita ni se
        da la validación administrativa (JP, 22-sep-2026)."""
        for order in self:
            unpriced = order.order_line.filtered(lambda l: l.printing_design_id and not l.printing_design_id.has_price).mapped('printing_design_id')
            if unpriced:
                raise UserError(_('La cotización %s no se puede validar: la ficha de estampado %s no tiene precio. '
                                  'Desarrollo debe colocarlo y marcarla como Hecho.',
                                  order.name, ', '.join(unpriced.mapped('display_name'))))

    def _check_quote_admin_approval(self):
        """Una cotización de tejido con el interruptor activo no se envía ni
        se convierte en pedido sin la validación administrativa."""
        for order in self:
            if order.is_quote and order.state == 'draft' and order._requires_quote_approval() and not order.admin_approval_user_id:
                raise UserError(_('La cotización %s requiere validación administrativa antes de enviarse al cliente. '
                                  'Usa el botón "Solicitar validación".', order.name))

    def _get_pricing_pricelist(self):
        self.ensure_one()
        return self.company_id.sales_pricelist_id or self.pricelist_id

    def _requires_sale_approval_workflow(self):
        self.ensure_one()
        return bool(
            not self.is_quote
            and self.is_company_produce
            and (self.company_id.sale_admin_approval or self.company_id.sale_finance_approval)
            and any(line.product_template_id.is_weaving for line in self.order_line)
        )

    def _requires_quote_approval(self):
        self.ensure_one()
        return bool(
            self.is_quote
            and self.is_company_produce
            and self.company_id.quotation_admin_approval
            and any(line.product_template_id.is_weaving for line in self.order_line)
        )

    def _confirmation_error_message(self):
        self.ensure_one()
        # Los estados pendientes son nuestros: confirmar desde ellos es válido
        # (aunque los interruptores se hayan apagado con el pedido en curso).
        if not self.is_quote and self.state in ('pending_admin_approval', 'pending_finance_approval'):
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
            # if any(not line.lab_dev_line_id for line in lines):
            #     raise UserError(_('Cant\'t confirm sale order without colors.'))
            # if rec.is_quote and rec.company_id.is_company_produce:
            #     raise UserError(_('Cant\'t confirm a quotation.'))

    def _subscribe_sale_approval_followers(self, levels=None):
        orders = self.filtered(lambda order: order.is_company_produce)
        if not orders:
            return

        approver_users = self.env['res.users']
        admin_group = self.env.ref('idtx_sale_order.group_sale_order_admin_approver', raise_if_not_found=False)
        finance_group = self.env.ref('idtx_sale_order.group_sale_order_finance_approver', raise_if_not_found=False)
        for order in orders:
            order_levels = levels or tuple(
                level for level, active in (
                    ('admin', order.company_id.sale_admin_approval),
                    ('finance', order.company_id.sale_finance_approval),
                ) if active)
            if 'admin' in order_levels and admin_group:
                approver_users |= admin_group.all_user_ids
            if 'finance' in order_levels and finance_group:
                approver_users |= finance_group.all_user_ids
        approver_users = approver_users.filtered(
            lambda user: user.active and user.partner_id
        )
        partner_ids = approver_users.mapped('partner_id').ids
        if partner_ids:
            orders.sudo().message_subscribe(partner_ids=partner_ids)

    def _run_sale_confirmation(self):
        self._validate_sale_confirmation_requirements()
        res = super(SaleOrder, self).action_confirm()
        for rec in self:
            # La creación de OF vive en la línea para reutilizarla al agregar
            # productos a un pedido ya confirmado.
            rec.order_line._create_weaving_productions()
            if not rec.company_id.is_company_produce or not rec.has_weaving_line:
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
        # Cotizaciones ya validadas: si cambian las líneas (productos,
        # cantidades, precios) la validación administrativa deja de valer y
        # hay que pedirla de nuevo.
        approved_quotes = self.filtered(
            lambda o: o.is_quote and o.state == 'draft' and o.admin_approval_user_id
        ) if 'order_line' in vals and 'admin_approval_user_id' not in vals else self.browse()
        res = super().write(vals)
        for quote in approved_quotes.filtered(lambda q: q._requires_quote_approval()):
            super(SaleOrder, quote).write({'admin_approval_user_id': False, 'admin_approval_date': False})
            quote.message_post(
                body=_('Validación administrativa anulada: se modificaron las líneas de la cotización. Solicítala de nuevo.'),
                message_type='comment', subtype_xmlid='mail.mt_note')
        if not self.env.context.get('skip_original_labdev_guard') and ('lab_dev_ids' in vals or 'order_line' in vals):
            self._ensure_original_lab_devs()
        if 'lab_dev_ids' in vals:
            self._cleanup_orphan_lab_dev_lines()
        if 'payment_term_id' in vals or 'incoterm' in vals or 'is_sample' in vals \
                or ('partner_id' in vals and any(self.mapped('is_sample'))):
            self._recompute_order_line_prices_from_terms()
        return res

    def _ensure_original_lab_devs(self):
        for order in self:
            if not order.id:
                continue
            original_lab_devs = self.env['lab.dev'].search([
                ('sale_order_id', '=', order.id),
                ('state', '!=', 'cancel'),
            ])
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
            # Al cambiar venta/servicio se vuelve a proponer toda la ruta con
            # precio del análisis (en servicio el vendedor luego quita fases).
            rec.order_line._onchange_route_operations()
            rec.order_line._onchange_product_or_color()
            # El tipo de proceso SITPRO debe ser de la misma clase que la venta.
            allowed = self.env['sitpro.sale.type']._order_kinds_for_sale_type(rec.sale_type)
            if rec.process_type_id and rec.process_type_id.order_kind not in allowed:
                rec.process_type_id = False

    @api.onchange('payment_term_id', 'incoterm', 'is_sample')
    def _onchange_payment_term_id(self):
        self._recompute_order_line_prices_from_terms()

    @api.onchange('partner_id')
    def _onchange_partner_id_sample_prices(self):
        # El recargo de muestra depende del cliente (sus precios de muestra).
        for order in self.filtered('is_sample'):
            order._recompute_order_line_prices_from_terms()

    @api.onchange('order_line')
    def _onchange_order_line_lab_dev_line_id(self):
        for order in self:
            # Mantener siempre los LD creados desde esta orden,
            # aunque temporalmente no aparezcan en las lineas.
            original_lab_devs = self.env['lab.dev']
            if order.id:
                original_lab_devs = self.env['lab.dev'].search([
                    ('sale_order_id', '=', order.id),
                    ('state', '!=', 'cancel'),
                ])
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
            raise UserError(_('Can\'t create Lab Dip some lines have no color name.'))
        today = fields.Date.context_today(self)
        production_company = self.company_id._get_production_company()
        lab_dev = self.env['lab.dev'].with_company(production_company).create({
            'lab_dev_date': today,
            'sale_order_id': self.id,
            'partner_id': self.partner_id.id,
            'company_id': production_company.id,
            # Vendedor del Lab Dip = vendedor del pedido (JP, 24-sep-2026).
            'user_id': self.user_id.id,
        })
        self.lab_dev_ids = self.lab_dev_ids | lab_dev

        # Se crea UNA línea de Lab Dip por cada color_name pendiente. Su
        # product_ids reúne TODOS los productos de las líneas de la orden con
        # ese color (base + complementos). Todas esas líneas comparten la
        # misma línea de Lab Dip (los complementos no crean una propia).
        pending = self.order_line.filtered(
            lambda l: l.product_template_id.is_weaving and l.is_lab_color and not l.lab_dev_line_id
        )
        seen = set()
        for color_name in pending.mapped('color_name'):
            if color_name in seen:
                continue
            seen.add(color_name)
            color_lines = self.order_line.filtered(
                lambda l: not l.display_type and l.color_name == color_name
            )
            pending_color_lines = color_lines.filtered(lambda l: not l.lab_dev_line_id)
            products = color_lines.mapped('product_template_id')
            ld_line = self.env['lab.dev.line'].create({
                'lab_dev_id': lab_dev.id,
                'product_ids': [Command.set(products.ids)],
                'color_name': (color_name or '').upper(),
                'sale_order_line_id': pending_color_lines[:1].id,
            })
            pending_color_lines.write({
                'color_name': (color_name or '').upper(),
                'lab_dev_line_id': ld_line.id,
            })

        # Se devuelve la acción para abrir el LD recién creado: sin el return,
        # el botón creaba el desarrollo y dejaba al usuario en el pedido, como
        # si no hubiera pasado nada.
        return self.open_labdev()
    
    def open_labdev(self):
        return self.lab_dev_ids._get_records_action(name=_("Lab Dip"))
    
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
                order.weaving_warning += _('This sale order has no price list or the option is not activated.') + '\n'
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
                            order.weaving_warning += _('Product %s has product %s on its bom and does not have a price in %s price list. The price is obtained from its own sale price.', line.product_id.product_tmpl_id.display_name, product.display_name, pricing_pricelist.name) + '\n'
                    # Procesos cotizados: fases del maestro desde la ruta del
                    # análisis del producto (ya no de la ficha/LdM).
                    operations = line._get_quoted_operations()
                    for operation in operations:
                        if operation.type_prices == 'col' and line.is_lab_color:
                            operation_color_line = operation.product_color_price_ids.filtered(
                                lambda p: p.product_color_id == line.product_color_id)
                            if not operation_color_line:
                                order.weaving_warning += _('The type prices of %s operation is by color. The color %s does not exists in the operation color list, product %s.', operation.name, line.product_color_id.name, line.product_id.product_tmpl_id.display_name) + '\n'
                # for line in order.order_line.filtered(lambda l: l.product_template_id.is_weaving):
                    if line.lab_dev_line_id and line.color_name:
                        if line.color_name.upper() != line.lab_dev_line_id.color_name.upper():
                            order.weaving_warning += _('Product %s color %s does not match lab color name %s.', line.product_id.product_tmpl_id.display_name, line.color_name, line.lab_dev_line_id.color_name) + '\n'
                            order.color_name_warning = True
                    else:
                        if not line.color_name:
                            line.color_name = line.lab_dev_line_id.color_name
                    if line.diff_days:                        
                        order.weaving_warning += _('Product %s has an old price. Quotation is %s days old', line.product_id.product_tmpl_id.display_name, line.diff_days) + '\n'
                    # if not line.product_template_id.bom_ids:
                    #     order.weaving_warning += _(('Product %s does not have any bom. Please check with product development.')  % line.product_id.product_tmpl_id.display_name) + '\n'
                    if not line.product_id.analysis_id.weaving_price:
                        order.weaving_warning += _('Product %s has no weaving price. Please check with product development', line.product_id.product_tmpl_id.display_name) + '\n'
                    # Ficha de estampado creada por el vendedor y aún sin precio de
                    # desarrollo: la cotización no se valida ni se envía (JP, 22-sep-2026).
                    if line.printing_design_id and not line.printing_design_id.has_price:
                        order.weaving_warning += _('La ficha de estampado %s del producto %s no tiene precio: desarrollo debe completarla antes de validar la cotización.',
                                                   line.printing_design_id.display_name, line.product_id.product_tmpl_id.display_name) + '\n'

                    # Cantidad por debajo del mínimo de producción: antes se
                    # aceptaba sin decir nada y el pedido llegaba a planta con
                    # una cantidad que no se puede tejer/teñir. Solo en el
                    # pedido de venta (is_quote=False): en la cotización no
                    # debe salir ni bloquear la creación del pedido. Una línea
                    # en 0 es una línea anulada (su OF se elimina): no avisa.
                    if not order.is_quote and line.min_qty and line.product_uom_qty and line.product_uom_qty < line.min_qty:
                        order.weaving_warning += _(
                            'El producto %(prod)s tiene %(qty)s %(uom)s y su '
                            'cantidad mínima es %(min)s: confirma con producción '
                            'antes de crear el pedido.',
                            prod=line.product_id.product_tmpl_id.display_name,
                            qty=line.product_uom_qty,
                            uom=line.product_uom_id.name or 'kg',
                            min=line.min_qty) + '\n'

                    has_weaving_operation = any(
                        operation.operation_type == 'weaving'
                        for operation in operations
                    )
                    if has_weaving_operation and line.order_id.sale_type == 'sale' and order.is_quote:
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
                                'Product %s has weaving operation but no thread items were found in price details.',
                                line.product_id.product_tmpl_id.display_name) + '\n'
                    if line.is_lab_color and not any(op.gives_color for op in operations):
                        order.weaving_warning += _('Product %s has a lab color %s but not operation to dieying.', line.product_id.product_tmpl_id.display_name, line.product_color_id.name) + '\n'

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
            if self.signed_on:
                self.locked = True
            return
        return super()._validate_order()

    def action_confirm(self):
        quote_orders = self.filtered(lambda order: order.is_quote)
        if quote_orders:
            return quote_orders._run_sale_confirmation()

        self.filtered(lambda order: not order.is_quote and order.is_company_produce and order.state not in ('sale', 'cancel'))._subscribe_sale_approval_followers()

        finance_orders = self.filtered(lambda order: order.state == 'pending_finance_approval' and order._requires_sale_approval_workflow())
        if finance_orders:
            res = finance_orders._run_sale_confirmation()
            # Mismo bloqueo que en action_finance_approve: aprobado
            # financieramente => pedido bloqueado.
            finance_orders.filtered(lambda o: o.state == 'sale').sudo().action_lock()
            return res

        # Pedidos de tejido de empresa productiva con AMBOS niveles apagados:
        # confirman directo, pero con la lógica textil (OF, etc.).
        direct_weaving_orders = self.filtered(
            lambda order: not order._requires_sale_approval_workflow() and order.is_company_produce and order.has_weaving_line)
        if direct_weaving_orders:
            return direct_weaving_orders._run_sale_confirmation()

        regular_orders = self.filtered(
            lambda order: not order._requires_sale_approval_workflow() and not (order.is_company_produce and order.has_weaving_line))
        if regular_orders:
            return super(SaleOrder, regular_orders).action_confirm()

        orders_to_submit = self.filtered(lambda order: order._requires_sale_approval_workflow() and order.state not in ('sale', 'cancel', 'pending_admin_approval', 'pending_finance_approval'))
        if orders_to_submit:
            return orders_to_submit.action_request_sale_approval()
        return True
    
    def action_create_sale_order(self):
        self.ensure_one()
        # La ficha (LdM) ya no se elige en la cotización (se asigna sola la
        # primera del producto) pero la OF del pedido la necesita: si un
        # producto no tiene ninguna, se indica cuál para pedirla a desarrollo.
        missing = self.order_line.filtered(lambda l: l.product_template_id.is_weaving and not l.bom_id)
        if missing:
            raise UserError(_(
                'All weaving lines must have a bill of materials to create a sale order. '
                'Products without technical sheet (BoM): %s',
                ', '.join(missing.mapped('product_template_id.display_name'))))
        if self.is_quote and self.weaving_warning:
            raise UserError(_('Please solve all the warnings first.'))
        if self.is_quote and self._requires_quote_approval() and not self.admin_approval_user_id:
            raise UserError(_('La cotización %s requiere validación administrativa antes de crear el pedido de venta.', self.name))
        sale_order = self.copy({
                'quotation_id': self.id,
                'is_quote': False,
            })
        self.action_lock()
        sale_order._recompute_order_line_prices_from_terms()
        self.sale_order_ids = [Command.link(sale_order.id)]
        return self.sale_order_ids._get_records_action(name=_("Sale Orders"))
    
    def _get_productions_to_cancel(self):
        """OF vivas del pedido: las enlazadas al pedido y las de sus líneas
        (incluye reposiciones creadas desde planta)."""
        self.ensure_one()
        return (self.production_ids | self.order_line.production_ids).filtered(
            lambda p: p.state != 'cancel')

    def _check_cancel_allowed(self):
        """Candado (JP, 22-sep-2026): un pedido cuya producción ya avanzó
        (rollos del cliente recibidos, rollos registrados, partidas,
        operaciones iniciadas, consumos) NO se cancela: hay que revertir el
        proceso a mano primero. Antes se cancelaban las OF 'confirmadas'
        aunque ya tuvieran recepciones y partidas."""
        for order in self:
            blockers = []
            for production in order._get_productions_to_cancel():
                reasons = production.sudo()._get_cancel_blockers()
                if reasons:
                    blockers.append('%s: %s' % (production.display_name, '; '.join(reasons)))
            if blockers:
                raise UserError(_(
                    'No se puede cancelar el pedido %(order)s porque su producción ya avanzó:\n'
                    '- %(details)s\n\n'
                    'Revierte primero todo el proceso a mano (cancelar partidas, recepciones y '
                    'rollos, deshacer consumos y traslados, cancelar las OF) y vuelve a intentarlo.',
                    order=order.name, details='\n- '.join(blockers)))
            for production in order._get_productions_to_cancel():
                if production.state not in ('draft', 'confirmed'):
                    state_label = dict(production._fields['state'].selection).get(production.state, production.state)
                    raise UserError(_('Can\'t cancel production in %s') % state_label)
            for labdev in order.lab_dev_ids.filtered(lambda ld: ld.sale_order_id == order):
                if labdev.state not in ('draft', 'cancel'):
                    state_label = dict(labdev._fields['state'].selection).get(labdev.state, labdev.state)
                    raise UserError(_('Can\'t cancel lab dev in %s') % state_label)

    def action_cancel(self):
        # Todas las validaciones ANTES de tocar nada: si algo bloquea, ni el
        # pedido ni sus OF ni sus Lab Dip cambian.
        self._check_cancel_allowed()
        res = super().action_cancel()
        for order in self.filtered(lambda o: o.state == 'cancel'):
            order._get_productions_to_cancel().sudo().action_cancel()
            for labdev in order.lab_dev_ids.filtered(lambda ld: ld.sale_order_id == order):
                labdev.sudo().action_cancel()
                for line in order.order_line.filtered(
                        lambda l: l.lab_dev_line_id and l.lab_dev_line_id.lab_dev_id == labdev):
                    line.lab_dev_line_id = False
            order.lab_dev_ids = order.lab_dev_ids.filtered(lambda ld: ld.state != 'cancel')
        return res
    
    @api.onchange('partner_id')
    def _onchange_partner_id(self):
        for rec in self:
            rec.applicant_id = False
