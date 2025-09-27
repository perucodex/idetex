from odoo import models, fields, api, _

class LabDev(models.Model):
    _name = 'lab.dev'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Laboratory Development'

    name = fields.Char('Name', copy=False, default=lambda self: _('New'))
    lab_dev_date = fields.Date('Lab Dev Date', default=fields.Date.context_today)
    sale_order_id = fields.Many2one('sale.order', string='Sale Order', ondelete='restrict')
    partner_id = fields.Many2one(related='sale_order_id.partner_id', ondelete='restrict')
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
        ('approved', 'Approved'),
    ], string='State', default='draft')

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
    _rec_name = 'color_name'

    lab_dev_id = fields.Many2one('lab.dev', string='Lab Dev')
    product_id = fields.Many2one('product.template','Product', ondelete='restrict')
    color_name = fields.Char('Color Name')
    color_code = fields.Char('Color Code')
    color = fields.Char('Color')
    color_process_type_id = fields.Many2one('color.process.type','Color Process Type', ondelete='restrict')
    fiber_id = fields.Many2one(related='color_process_type_id.fiber_id')
    color_range_id = fields.Many2one('color.range','Color Range', ondelete='restrict')
    color_intensity_id = fields.Many2one('color.intensity','Color Intensity', ondelete='restrict')
    color_recipe_ids = fields.One2many('color.recipe', 'lab_dev_line_id', string='Recipes')
    bath_ratio = fields.Integer('Bath Ratio')
    sale_order_line_id = fields.Many2one('sale.order.line', string='Sale Order Line')
    state = fields.Selection([
        ('process', 'Process'),
        ('approved', 'Approved'),
    ], string='State', default='process')
    available_product_ids = fields.Many2many(
        'product.template',
        compute='_compute_available_products',
        string='Available Products'
    )

    @api.depends('lab_dev_id.sale_order_id')
    def _compute_available_products(self):
        for record in self:
            products = self.env['product.template'].search([('is_weaving','=', True)])
            if record.lab_dev_id.sale_order_id:
                products = record.lab_dev_id.sale_order_id.order_line.mapped('product_template_id').ids
            record.available_product_ids = products
    
    @api.onchange('color_process_type_id','color_range_id','color_intensity_id')
    def _onchange_color_code(self):
        for rec in self:
            # Verifica que los tres campos requeridos estén presentes
            if rec.color_process_type_id and rec.color_range_id and rec.color_intensity_id:
                prefix = (rec.color_process_type_id.code or '') + \
                        (rec.color_range_id.code or '') + \
                        (rec.color_intensity_id.code or '')

                # Busca los registros existentes con ese mismo prefijo
                last_line = self.env['lab.dev.line'].search(
                    [('color_code', 'like', f'{prefix}%')],
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
                rec.color_code = (rec.color_process_type_id.code or '') + \
                        (rec.color_range_id.code or '') + \
                        (rec.color_intensity_id.code or '')