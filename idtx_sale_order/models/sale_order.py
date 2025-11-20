from odoo import models, fields, Command, api, _
from odoo.exceptions import UserError

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
    ], string='Sale Type', default='sale')
    production_count = fields.Integer('Production Count', compute='_compute_production_count')
    sale_count = fields.Integer('Sales Count', compute='_compute_sale_count')
    is_quote = fields.Boolean('is_quote', default=True)
    # is_manual_lab_dev = fields.Boolean('is_manual_lab_dev', default=False)
    lab_dev_count = fields.Integer(string="Technical Sheet Count", compute='_compute_lab_dev_count')
    is_company_produce = fields.Boolean(related='company_id.is_company_produce')
    need_labdev = fields.Boolean('Need LabDev?', compute='_compute_need_labdev', default=False)
    
    @api.depends('order_line')
    def _compute_need_labdev(self):
        for rec in self:
            rec.need_labdev = any(line.product_template_id.is_weaving for line in self.order_line)

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

    @api.onchange('lab_dev_ids')
    def _onchange_lab_dev_ids(self):
        for line in self.order_line:
            ld_line = self.lab_dev_ids._origin.lab_dev_line_ids.filtered(lambda l: l.sale_order_line_id == line._origin)
            if ld_line:
                line.lab_dev_line_id = ld_line
            # else:
            #     line.lab_dev_line_id = False

    def create_labdev(self):
        if any(not line.color_name for line in self.order_line.filtered(lambda l: l.product_template_id.is_weaving)):
            raise UserError(_('Can\'t create Lab Dev some lines have no color name.'))
        today = fields.Date.context_today(self)
        data = {
            'lab_dev_date': today,
            'sale_order_id': self.id,
            'partner_id': self.partner_id.id,
            'lab_dev_line_ids': [Command.create({
                 'product_id': line.product_template_id.id,
                 'color_name': line.color_name or line.product_color_id.name,
                 'sale_order_line_id': line.id,
            }) for line in self.order_line.filtered(lambda l: l.product_template_id.is_weaving)]
        }
        lab_dev = self.env['lab.dev'].create(data)
        self.lab_dev_ids = [Command.link(lab_dev.id)]
        self.open_labdev()
    
    def open_labdev(self):
        return self.lab_dev_ids._get_records_action(name=_("Lab Dev"))
    
    def open_productions(self):
        return self.order_line.production_id._get_records_action(name=_("Productions"))
    
    def open_sales(self):
        return self.sale_order_ids._get_records_action(name=_("Sale Orders"))
    
    @api.depends('order_line','partner_id','pricelist_id')
    def _compute_weaving_warning(self):
        for order in self:
            order.weaving_warning = ''
            if order.partner_id and not order.pricelist_id:
                order.weaving_warning += _(('This sale order has no price list or the option is not activated.')) + '\n'
            else:
                for line in order.order_line.filtered(lambda l: l.product_template_id.is_weaving):
                    if line.product_template_id.bom_ids:    
                        bom_id = line.product_template_id.bom_ids[0]
                        for bom_line in bom_id.bom_line_ids:
                            pricelist_item_id = line.order_id.pricelist_id._get_product_rule(
                                bom_line.product_id.product_tmpl_id,
                                quantity=bom_line.product_qty or 1.0,
                                uom=bom_line.product_uom_id,
                                date=line._get_order_date(),
                            )
                            if not pricelist_item_id and order.partner_id:
                                order.weaving_warning += _(('Product %s has product %s on its bom and does not have a price in %s price list. The price is obtained from its own sale price.') %( line.product_id.product_tmpl_id.name, bom_line.product_id.product_tmpl_id.name, order.pricelist_id.name)) + '\n'
                        for operation in bom_id.operation_ids:
                            if operation.operation_id.type_prices == 'col':
                                operation_color_line = operation.operation_id.product_color_price_ids.search([('product_color_id','=',line.product_color_id.id),('mrwo_id','=', operation.operation_id.id)])
                                if not operation_color_line:
                                    order.weaving_warning += (_('The type prices of %s operation is by color. The color %s does not exists in the operation color list of product %s.') %(operation.operation_id.name, line.product_color_id.name, line.product_id.product_tmpl_id.name)) + '\n'
                for line in order.order_line.filtered(lambda l: l.product_template_id.is_weaving):
                    if line.lab_dev_line_id and line.color_name:
                        if line.color_name.upper() != line.lab_dev_line_id.color_name.upper():
                            order.weaving_warning += (_('Product %s color %s does not match lab color name %s.') %(line.product_id.product_tmpl_id.name, line.color_name, line.lab_dev_line_id.color_name)) + '\n'
                    else:
                        if not line.color_name:
                            line.color_name = line.lab_dev_line_id.color_name
                    if line.diff_days:                        
                        order.weaving_warning += _(('Product %s has an old price. Quotation is %s days old') %( line.product_id.product_tmpl_id.name, line.diff_days)) + '\n'
                    if not line.product_template_id.bom_ids:
                        order.weaving_warning += _(('Product %s  does not have any bom. Please check with product development.')  % line.product_id.product_tmpl_id.name) + '\n'

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
    
    def action_confirm(self):
        for rec in self:
            if not rec.lab_dev_ids and rec.company_id.is_company_produce and any(line.product_template_id.is_weaving for line in self.order_line):
                raise UserError(_('Cant\'t confirm sale order without LD'))
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
                    })
                    # wo_to_delete = prd.workorder_ids.filtered(lambda wo: wo.mrwo_id in operations_to_delete)
                    # wo_to_delete.unlink()
                    line.production_id = prd
                    if prd.color_recipe_id:
                        prd.action_confirm()
                    prd.do_unreserve()
        return res
    
    def action_create_sale_order(self):
        self.ensure_one()
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