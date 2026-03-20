from odoo import models, fields, api, _
from odoo.exceptions import UserError
from odoo.fields import Domain

class LabDev(models.Model):
    _name = 'lab.dev'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Laboratory Development'
    _order = 'name desc'

    name = fields.Char('Name', copy=False, default=lambda self: _('New'))
    lab_dev_date = fields.Date('Lab Dev Date', default=fields.Date.context_today)
    sale_order_id = fields.Many2one('sale.order', string='Sale Order', ondelete='restrict')
    partner_id = fields.Many2one('res.partner', 'Customer', ondelete='restrict')
    recipe_count = fields.Integer('Recipe Count', compute='_compute_recipe_count')
    volume = fields.Float('Volume')
    kilos = fields.Float('Kilos')
    lab_dev_line_ids = fields.One2many('lab.dev.line', 'lab_dev_id', string='Lab Dev Lines')
    color_recipe_ids = fields.One2many(related='lab_dev_line_ids.color_recipe_ids')
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
        index=True,
        required=True
    )
    state = fields.Selection([
        ('draft', 'Draft'),
        ('dev', 'Development'),
        ('done', 'Done'),
    ], string='State', default='draft', tracking=True)
    
    def action_development(self):
        self.state = 'dev'

    def action_done(self):
        if any(line.state != 'done' for line in self.lab_dev_line_ids):
            raise UserError(_('All lab dev lines must be done before marking the lab dev as done.'))
        self.state = 'done'

    def open_recipes(self):
        return self.lab_dev_line_ids.color_recipe_ids._get_records_action(name=_('Recipes'), context={'group_by': 'color_name'})
    
    @api.depends('lab_dev_line_ids')
    def _compute_recipe_count(self):
        for rec in self:
            rec.recipe_count = len(rec.lab_dev_line_ids.color_recipe_ids)
    
    #=== CRUD METHODS ===#

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                seq_date = fields.Datetime.context_timestamp(
                    self, fields.Datetime.to_datetime(vals['lab_dev_date'])
                ) if 'lab_dev_date' in vals else None
                vals['name'] = self.env['ir.sequence'].with_company(vals.get('company_id')).next_by_code(
                    'lab.dev', sequence_date=seq_date) or _('New')

        return super().create(vals_list)
    
class LabDevLine(models.Model):
    _name = 'lab.dev.line'
    _description = 'Laboratory Development Line'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'color_name'

    lab_dev_id = fields.Many2one('lab.dev', string='Lab Dev', ondelete='cascade')
    # product_id = fields.Many2one('product.template','Product', ondelete='restrict')
    color_name = fields.Char('Color Name')
    color_code = fields.Char('Color Code')
    color = fields.Char('Color')
    color_process_type_id = fields.Many2one('color.process.type','Color Process Type', ondelete='restrict')
    fiber_id = fields.Many2one(related='color_process_type_id.fiber_id')
    color_range_id = fields.Many2one('color.range','Color Range', ondelete='restrict')
    color_intensity_id = fields.Many2one('color.intensity','Color Intensity', ondelete='restrict')
    color_recipe_ids = fields.One2many('color.recipe', 'lab_dev_line_id', string='Recipes')
    bath_ratio = fields.Integer('Bath Ratio')
    sale_order_id = fields.Many2one(related='lab_dev_id.sale_order_id')
    sale_order_line_id = fields.Many2one('sale.order.line', string='Sale Order Line')
    state = fields.Selection([
        ('test', 'Test'),
        ('color', 'Colorfastness'),
        ('approved', 'Approved'),
    ], string='State', default='test', tracking=True)
    available_product_ids = fields.Many2many(
        'product.template',
        compute='_compute_available_products',
        string='Available Products'
    )
    display_name = fields.Char(
            string='Display Name',
            compute='_compute_display_name',
            store=True,
        )
    colorfastness_washing_id = fields.Many2one('colorfastness.washing', string='Colorfastness to Washing', ondelete='cascade')

    @api.depends('color_code', 'color_name')
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = f"[{rec.color_code or ''}] {rec.color_name or ''}".strip()
        
    @api.model
    def name_search(self, name='', domain=None, operator='ilike', limit=100):
        base_domain = Domain(domain or Domain.TRUE)
        if name:
            base_domain &= Domain('color_code', operator, name) | Domain('color_name', operator, name)
        return [(rec.id, rec.display_name) for rec in self.search(base_domain, limit=limit)]
    
    @api.depends('sale_order_id')
    def _compute_available_products(self):
        for record in self:
            products = self.env['product.template'].search([('is_weaving','=', True)])
            if record.sale_order_id:
                products = record.sale_order_id.order_line.mapped('product_template_id').filtered(lambda p: p.is_weaving).ids
            record.available_product_ids = products
    
    @api.onchange('color_process_type_id','color_range_id','color_intensity_id','color_recipe_ids')
    def _onchange_color_code(self):
        for rec in self:
            # Verifica que los tres campos requeridos estén presentes
            if rec.color_process_type_id and rec.color_range_id and rec.color_intensity_id:
                prefix = (rec.color_process_type_id.code or '') + \
                        (rec.color_range_id.code or '') + \
                        (rec.color_intensity_id.code or '')

                # Busca los registros existentes con ese mismo prefijo
                last_line = self.env['lab.dev.line'].search(
                    [('color_code', '=like', f'{prefix}%')],
                    order='color_code desc',
                    limit=1
                )

                if last_line:
                    last_counter_str = last_line.color_code[-4:]
                    try:
                        last_counter = int(last_counter_str)
                    except ValueError:
                        last_counter = 0
                    next_counter = str(last_counter + 1).zfill(4)
                else:
                    next_counter = '0001'

                # Asigna el nuevo código
                rec.color_code = prefix + next_counter
            else:
                rec.color_code = ''
                # (rec.color_process_type_id.code or '') + \
                #         (rec.color_range_id.code or '') + \
                #         (rec.color_intensity_id.code or '')
                
    @api.model_create_multi
    def create(self, vals_list):
        for rec in self:
            rec.colorfastness_washing_id = self.env['colorfastness.washing'].create({})
        return super().create(vals_list)

    def unlink(self):
        if any(r.state == 'approved' for r in self.color_recipe_ids):
            raise UserError(_('Can\'t delete a lab dev with recipes in approved state.'))
        return super().unlink()
    
    # Funcion escondida para actualizar los registros de laboratorio con un registro de solidez al lavado, para pruebas y desarrollo solamente
    def action_update(self):
        labs = self.env['lab.dev.line'].search([])
        for rec in labs:
            rec.colorfastness_washing_id = self.env['colorfastness.washing'].create({
                'color_change_degree': 2,
                'migration_acetate': 2,
                'migration_cotton': 2,
                'migration_nylon': 2,
                'migration_polyester': 2,
                'migration_acrylic': 2,
                'migration_wool': 2,
                'colorfastness_to_dry_rubbing': 2,
                'colorfastness_to_wet_rubbing': 2,
            })