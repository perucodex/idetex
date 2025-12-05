from odoo import fields, models, api, _
from odoo.fields import Command
from odoo.exceptions import ValidationError
from collections import defaultdict
import mysql.connector

class MenuInvoice(models.Model):
    _name = 'menu.invoice'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Menu Invoice'

    name = fields.Char('Name', required=True, copy=False, readonly=False, default=lambda self: _('New'))
    start_date = fields.Date('Start Date', required=True, default=lambda self: fields.Date.context_today(self))
    end_date = fields.Date('End Date', required=True, default=lambda self: fields.Date.context_today(self))
    tax_id = fields.Many2one('account.tax', string='Tax', required=True)
    company_ids = fields.Many2many('res.partner', string='Companies')
    line_ids = fields.One2many('menu.invoice.line', 'menu_invoice_id', string='line')
    invoice_ids = fields.Many2many('account.move', string='Invoices')
    invoice_count = fields.Integer(compute='_compute_invoice_count')
    state = fields.Selection([
        ('draft', 'Draft'),
        ('data', 'Data'),
        ('done', 'Done'),
    ], string='State', default='draft')
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
        index=True,
        required=True
    )

    def _compute_invoice_count(self):
        for rec in self:
            rec.invoice_count = len(self.invoice_ids)

    #=== CRUD METHODS ===#

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _("New")) == _("New"):
                seq_date = fields.Datetime.context_timestamp(
                    self, fields.Datetime.to_datetime(vals['start_date'])
                ) if 'start_date' in vals else None
                vals['name'] = self.env['ir.sequence'].with_company(vals.get('company_id')).next_by_code(
                    'menu.invoice.sequence', sequence_date=seq_date) or _("New")

        return super().create(vals_list)
    
    # -------------------------------------------------------------------------
    # CONSTRAINT METHODS
    # -------------------------------------------------------------------------
    @api.constrains('start_date', 'end_date', 'company_id')
    def _check_dates(self):
        for mi in self:
            # Starting date must be prior to the ending date
            start_date = mi.start_date
            end_date = mi.end_date
            if end_date < start_date:
                raise ValidationError(_('The ending date must not be prior to the starting date.'))

            domain = [
                ('id', '!=', mi.id),
                ('company_id', '=', mi.company_id.id),
                ('company_ids', 'in', mi.company_ids),
                '|', '|',
                '&', ('start_date', '<=', mi.start_date), ('end_date', '>=', mi.start_date),
                '&', ('start_date', '<=', mi.end_date), ('end_date', '>=', mi.end_date),
                '&', ('start_date', '<=', mi.start_date), ('end_date', '>=', mi.end_date),
            ]

            if self.search_count(domain) > 0:
                raise ValidationError(_('You can not have an overlap between menu invoices, please correct the start and/or end dates.'))

    def action_process(self):
        # Primero los menus pagados para boletear
        self._create_lines(self._action_get_data(True), True)
        # Luego facturamos a las empresas
        self._create_lines(self._action_get_data())
    
    def get_query(self, paid=False):
        placeholder = ','.join(f"'{vat}'" for vat in self.company_ids.mapped('vat'))
        start = self.start_date
        end = self.end_date
        if paid:
            query = f"""
                SELECT ed.fecha,
                    ed.codigo,
                    ed.item,
                    p.menuweb,
                    IF(ed.cant_postre = 0, ed.precio, ps.precio) AS precio,
                    ed.pago,
                    ed.pagado,
					SUM(IF(ed.cant_postre = 0, 1, ed.cant_postre)) AS cant_postre,
                    ed.postre,
                    ps.sopa,
                    tr.empresa
                FROM estado_diario ed
                LEFT JOIN programacion p ON p.fecha = ed.fecha AND p.item = ed.item
                LEFT JOIN trabajadores tr ON tr.codigo = ed.codigo
                LEFT JOIN platos_sopas ps ON ps.cod_sopa = ed.postre
                WHERE ed.fecha >= '{start}'
                and ed.fecha <= '{end}'
                AND ed.pago = 1
                AND ed.item > 0
                AND tr.ruc in ({placeholder})
                GROUP BY ed.codigo, ed.item;
                """
        else:
            query = f"""
                SELECT ed.fecha,
                    tr.ruc,
                    ed.item,
                    p.menuweb,
                    IF(ed.cant_postre = 0, ed.precio, ps.precio) AS precio,
                    ed.pago,
                    ed.pagado,
					SUM(IF(ed.cant_postre = 0, 1, ed.cant_postre)) AS cant_postre,
                    ed.postre,
                    ps.sopa,
                    tr.empresa
                FROM estado_diario ed
                LEFT JOIN programacion p ON p.fecha = ed.fecha AND p.item = ed.item
                LEFT JOIN trabajadores tr ON tr.codigo = ed.codigo
                LEFT JOIN platos_sopas ps ON ps.cod_sopa = ed.postre
                WHERE ed.fecha >= '{start}'
                and ed.fecha <= '{end}'
                AND ed.pago = 0
                AND ed.item > 0
                AND tr.ruc in ({placeholder})                
                GROUP BY tr.ruc, ed.item, precio;
                """
        return query
        
    def _action_get_data(self, paid=False):
        conn1 = mysql.connector.connect(
            host="172.16.64.13",
            user="comedor",
            password="Xy5e49@2y7x",
            database="johnadm7_comedor",
            port=3306
        )
        conn2 = mysql.connector.connect(
            host="172.16.64.13",
            user="comedor",
            password="Xy5e49@2y7x",
            database="comedor_lurin",
            port=3306
        )
        cursor1 = conn1.cursor(dictionary=True)
        cursor2 = conn2.cursor(dictionary=True)
        query = self.get_query(paid)
        cursor1.execute(query)
        cursor2.execute(query)
        rows = cursor1.fetchall() 
        rows += cursor2.fetchall()
        cursor1.close()
        cursor2.close()
        conn1.close()
        conn2.close()

        return rows
    
    def _create_lines(self, rows, paid=False):
        vals = []
        for row in rows:
            if paid:
                partner_id = self.env['res.partner'].search([('vat','=', row['codigo'])], limit=1)
                if not partner_id:
                    partner_id = self.env['res.partner'].search([('vat','=', '00000000')])
            else:
                partner_id = self.env['res.partner'].search([('name','=', row['empresa'].strip())], limit=1)
                if not partner_id:
                    partner_id = self.env['res.partner'].create({'name': row['empresa'], 'company_type': 'company', 'l10n_latam_identification_type_id': self.env.ref('l10n_pe.it_RUC').id})
            if row['item'] in range(1,9):
                menu_type = '1'
            elif row['item'] in range(10,19):
                menu_type = str(row['item'])
            elif row['item'] > 19:
                menu_type = '20'
            if menu_type == '1':
                description = _('Menu')
            if menu_type == '11':
                description = _('Dinner')
            elif menu_type == '10':
                description = _('Breakfast')
            elif menu_type == '20':
                description = row['sopa']
            else:
                description = _('Menu')
            vals.append({
                'partner_id': partner_id.id,
                'menu_type': menu_type,
                'line_description': row['menuweb'] if row['menuweb'] else row['sopa'] or description,
                'description': description + _(' from: ') + self.start_date.strftime("%d/%m/%Y") + _(' to: ') + self.end_date.strftime("%d/%m/%Y"),
                'qty': row['cant_postre'],
                'price': row['precio'],
            })
        self.line_ids = [Command.create(val) for val in vals]
        self.state = 'data'

    def action_create_invoices(self):
        account_move = self.env['account.move']
        invoice_map = {}  # partner_id -> factura
        line_groups = defaultdict(float)  # (partner, desc, price) -> qty acumulada
        today = fields.Date.context_today(self)

        # 1. Acumulamos cantidades por (partner, descripción, precio)
        for line in self.line_ids:
            key = (line.partner_id.id, line.description or _('Menu'), line.price)
            line_groups[key] += line.qty or 1

        # 2. Creamos una factura por cliente con sus líneas agrupadas
        for (partner_id, description, price), qty in line_groups.items():
            partner = self.env['res.partner'].browse(partner_id)

            if partner_id in invoice_map:
                invoice = invoice_map[partner_id]
                invoice.write({
                    'invoice_line_ids': [Command.create({
                        'product_id': self.env.ref('idtx_menu_invoice_pe.product_template_product_menu').id,
                        'name': description,
                        'quantity': qty,
                        'product_uom_id': self.env.ref('uom.product_uom_unit').id,
                        'price_unit': price,
                        'tax_ids': [Command.link(self.tax_id.id)],
                    })]
                })
            else:
                invoice = account_move.create({
                    'partner_id': partner.id,
                    'invoice_date': today,
                    'date': today,
                    'currency_id': self.env.company.currency_id.id,
                    'move_type': 'out_invoice',
                    'invoice_line_ids': [Command.create({
                        'product_id': self.env.ref('idtx_menu_invoice_pe.product_template_product_menu').id,
                        'name': description,
                        'quantity': qty,
                        'product_uom_id': self.env.ref('uom.product_uom_unit').id,
                        'price_unit': price,
                        'tax_ids': [Command.link(self.tax_id.id)],
                    })]
                })
                invoice_map[partner_id] = invoice

        self.invoice_ids = [Command.link(inv.id) for inv in invoice_map.values()]
        self.state = 'done'

    def action_return(self):
        if any(inv.state in ('posted', 'cancel') for inv in self.invoice_ids):
            raise ValidationError(_('You can\'t return this document, some invoices are already posted or canceled'))
        if self.state == 'data':
            self.line_ids= [Command.clear()]
            self.state = 'draft'
        else:
            self.invoice_ids.unlink()
            self.state = 'data'
    
    def open_invoices(self):
        return self.invoice_ids._get_records_action(
            name=_("Invoices"),
            views_id='account.view_out_invoice_tree' if len(self.invoice_ids) > 1 else 'account.view_move_form',
            context={'default_move_type': 'out_invoice', 'search_default_l10n_latam_document_type': 1}
        )
    
class MenuInvoiceLine(models.Model):
    _name = 'menu.invoice.line'
    _description = 'Menu Invoice Line'

    menu_invoice_id = fields.Many2one('menu.invoice', string='Menu Invoice')
    partner_id = fields.Many2one('res.partner', string='Customer')
    menu_type = fields.Selection([
        ('1', 'Menu'),
        ('10', 'Breakfast'),
        ('11', 'Dinner'),
        ('20', 'Dessert'),
    ], string='Menu Type')
    line_description = fields.Char('Menu Description')
    description = fields.Char('Description')
    qty = fields.Integer('Qty')
    price = fields.Float('Price')