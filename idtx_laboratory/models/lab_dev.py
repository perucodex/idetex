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
        ('cancel', 'Cancelled'),
    ], string='State', default='draft', tracking=True)
    sub_partner_id = fields.Many2one('res.partner', 'Sub-Cliente', ondelete='restrict')
    user_id = fields.Many2one('res.users', string='Vendedor')
    testing = fields.Selection([('si', 'SI'), ('no', 'NO')], string='Testing')

    # FICHA TECNICA
    # LUCES
    light_primary = fields.Selection([
        ('d65', 'D65'),
        ('cfw', 'CFW o COLLWHITE'),
        ('tl84', 'TL84'),
        ('a', 'A'),
        ('u3000', 'U3000'),
        ('uv', 'UV'),
        ('ninguno', 'NINGUNO')
    ], string='Primaria')
    light_secondary = fields.Selection([
        ('d65', 'D65'),
        ('cfw', 'CFW o COLLWHITE'),
        ('tl84', 'TL84'),
        ('a', 'A'),
        ('u3000', 'U3000'),
        ('uv', 'UV'),
        ('ninguno', 'NINGUNO')
    ], string='Secundaria')
    light_others = fields.Selection([
        ('d65', 'D65'),
        ('cfw', 'CFW o COLLWHITE'),
        ('tl84', 'TL84'),
        ('a', 'A'),
        ('u3000', 'U3000'),
        ('uv', 'UV'),
        ('ninguno', 'NINGUNO')
    ], string='Otros')

    # PRODUCCION
    production_type = fields.Selection([
        ('solo_desarrollo', 'SOLO DESARROLLO'),
        ('lavanderia', 'LAVANDERIA'),
        ('muestra_vendedores', 'MUESTRA VENDEDORES'),
        ('prod_menor_50', 'PRODUCCION MENOR A 50 Kg'),
        ('prod_50_200', 'PRODUCCION 50 - 200 kG'),
        ('prod_mas_200', 'PRODUCCION MAS DE 200 Kg')
    ], string='Tipo de Prod')
    dyeing_type = fields.Char('Tipo de Teñido')
    finishing_type = fields.Char('Tipo de Acabado')
    treatment = fields.Char('Tratamiento')

    # SUAVIZADOS
    softening_dry = fields.Boolean('SECO')
    softening_silicone = fields.Boolean('SUAVIZADO SILICONADO')
    softening_lubricant = fields.Boolean('LUBRICANTE COSTURA')
    softening_resin = fields.Boolean('RESINADO')
    softening_exhaustion = fields.Boolean('SUAVIZADO HILO X AGOT..')
    softening_double_fiber = fields.Boolean('SUAVIZADO DOBLE FIBRA')
    softening_polyester = fields.Boolean('SUAVIZADO POLIESTER')

    # SOLIDECES
    fastness_washing = fields.Selection([
        ('1_malo', '1 MALO'),
        ('1-2_malo', '1-2 MALO'),
        ('2_malo', '2 MALO'),
        ('2-3_regular', '2-3 REGULAR'),
        ('3_regular', '3 REGULAR'),
        ('3-4_regular', '3-4 REGULAR'),
        ('4_bueno', '4 BUENO'),
        ('4-5_bueno', '4-5 BUENO'),
        ('5_excelente', '5 EXCELENTE'),
        ('ninguno', 'NINGUNO')
    ], string='Lavado')
    fastness_light = fields.Selection([
        ('1_malo', '1 MALO'),
        ('1-2_malo', '1-2 MALO'),
        ('2_malo', '2 MALO'),
        ('2-3_regular', '2-3 REGULAR'),
        ('3_regular', '3 REGULAR'),
        ('3-4_regular', '3-4 REGULAR'),
        ('4_bueno', '4 BUENO'),
        ('4-5_bueno', '4-5 BUENO'),
        ('5_excelente', '5 EXCELENTE'),
        ('ninguno', 'NINGUNO')
    ], string='Luz')
    fastness_dry_rubbing = fields.Selection([
        ('1_malo', '1 MALO'),
        ('1-2_malo', '1-2 MALO'),
        ('2_malo', '2 MALO'),
        ('2-3_regular', '2-3 REGULAR'),
        ('3_regular', '3 REGULAR'),
        ('3-4_regular', '3-4 REGULAR'),
        ('4_bueno', '4 BUENO'),
        ('4-5_bueno', '4-5 BUENO'),
        ('5_excelente', '5 EXCELENTE'),
        ('ninguno', 'NINGUNO')
    ], string='Frote Seco')
    fastness_wet_rubbing = fields.Selection([
        ('1_malo', '1 MALO'),
        ('1-2_malo', '1-2 MALO'),
        ('2_malo', '2 MALO'),
        ('2-3_regular', '2-3 REGULAR'),
        ('3_regular', '3 REGULAR'),
        ('3-4_regular', '3-4 REGULAR'),
        ('4_bueno', '4 BUENO'),
        ('4-5_bueno', '4-5 BUENO'),
        ('5_excelente', '5 EXCELENTE'),
        ('ninguno', 'NINGUNO')
    ], string='Frote Humedo')
    fastness_sublimation = fields.Selection([
        ('1_malo', '1 MALO'),
        ('1-2_malo', '1-2 MALO'),
        ('2_malo', '2 MALO'),
        ('2-3_regular', '2-3 REGULAR'),
        ('3_regular', '3 REGULAR'),
        ('3-4_regular', '3-4 REGULAR'),
        ('4_bueno', '4 BUENO'),
        ('4-5_bueno', '4-5 BUENO'),
        ('5_excelente', '5 EXCELENTE'),
        ('ninguno', 'NINGUNO')
    ], string='Sublimación')

    technical_observations = fields.Text('Observaciones')
    
    def action_development(self):
        for rec in self.lab_dev_line_ids:
            rec.colorfastness_washing_id = self.env['colorfastness.washing'].create({})
        self.state = 'dev'

    def action_done(self):
        if any(line.state != 'done' for line in self.lab_dev_line_ids):
            raise UserError(_('All lab dev lines must be done before marking the lab dev as done.'))
        self.state = 'done'

    def action_cancel(self):
        if any(line.state == 'done' for line in self.lab_dev_line_ids):
            raise UserError(_('Can\'t cancel a lab dev with lines in done state.'))
        self.state = 'cancel'

    def action_reset(self):
        self.state = 'draft'
        # self.lab_dev_line_ids.write({'state': 'test'})

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
    product_ids = fields.Many2many(
        'product.template', 'lab_dev_line_product_template_rel',
        'lab_dev_line_id', 'product_template_id', string='Products')
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
    ant = fields.Boolean('Ant')
    esm = fields.Boolean('Esm')
    per = fields.Boolean('Per')
    oxi = fields.Boolean('Oxi')
    weaving_type = fields.Selection([
        ('abierto', 'ABIERTO'),
        ('tubular', 'TUBULAR')
    ], string='Tipo Tej.', default='abierto')
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
    
    # Related fields for direct editing
    color_change_degree = fields.Float(related='colorfastness_washing_id.color_change_degree', readonly=False, store=True)
    migration_acetate = fields.Float(related='colorfastness_washing_id.migration_acetate', readonly=False, store=True)
    migration_cotton = fields.Float(related='colorfastness_washing_id.migration_cotton', readonly=False, store=True)
    migration_nylon = fields.Float(related='colorfastness_washing_id.migration_nylon', readonly=False, store=True)
    migration_polyester = fields.Float(related='colorfastness_washing_id.migration_polyester', readonly=False, store=True)
    migration_acrylic = fields.Float(related='colorfastness_washing_id.migration_acrylic', readonly=False, store=True)
    migration_wool = fields.Float(related='colorfastness_washing_id.migration_wool', readonly=False, store=True)
    colorfastness_to_dry_rubbing = fields.Float(related='colorfastness_washing_id.colorfastness_to_dry_rubbing', readonly=False, store=True)
    colorfastness_to_wet_rubbing = fields.Float(related='colorfastness_washing_id.colorfastness_to_wet_rubbing', readonly=False, store=True)
    light_fastness_light = fields.Float(related='colorfastness_washing_id.light_fastness_light', readonly=False, store=True)

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
                
    # @api.model_create_multi
    # def create(self, vals_list):
    #     for rec in self:
    #         rec.colorfastness_washing_id = self.env['colorfastness.washing'].create({})
    #     return super().create(vals_list)

    def unlink(self):
        if any(r.state == 'approved' for r in self.color_recipe_ids):
            raise UserError(_('Can\'t delete a lab dev with recipes in approved state.'))
        return super().unlink()
    
    # Funcion escondida para actualizar los registros de laboratorio con un registro de solidez al lavado, para pruebas y desarrollo solamente
    def action_update(self):
        labs = self.env['lab.dev.line'].search([])
        for rec in labs:
            rec.colorfastness_washing_id = self.env['colorfastness.washing'].create({
                'color_change_degree': 4,
                'migration_acetate': 3,
                'migration_cotton': 3,
                'migration_nylon': 3,
                'migration_polyester': 3,
                'migration_acrylic': 3,
                'migration_wool': 3,
                'colorfastness_to_dry_rubbing': 4,
                'colorfastness_to_wet_rubbing': 3,
            })