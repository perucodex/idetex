from odoo import models, fields, api, _

class ColorRecipe(models.Model):
    _name = 'color.recipe'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Color Recipe'

    product_color_id = fields.Many2one('product.color', 'Product Color')
    name = fields.Char('Name', copy=False, default=lambda self: _('New'))
    partner_id = fields.Many2one('res.partner', string='Customer')
    recipe_date = fields.Date('Recipe Date', default=fields.Date.context_today, copy=False)
    color_code = fields.Char('Color Code', compute='_compute_color_code')
    color_process_type_id = fields.Many2one('color.process.type','Color Process Type')
    fiber_id = fields.Many2one(related='color_process_type_id.fiber_id')
    color_range_id = fields.Many2one('color.range','Color Range')
    color_intensity_id = fields.Many2one('color.intensity','Color Intensity')
    color = fields.Char('Color')
    state = fields.Selection([
        ('draft', 'Draft'),
        ('test', 'Test'),
        ('approved', 'Approved'),
    ], string='State', default='draft')
    
    #=== CRUD METHODS ===#

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _("New")) == _("New"):
                seq_date = fields.Datetime.context_timestamp(
                    self, fields.Datetime.to_datetime(vals['recipe_date'])
                ) if 'recipe_date' in vals else None
                vals['name'] = self.env['ir.sequence'].with_company(vals.get('company_id')).next_by_code(
                    'color.recipe', sequence_date=seq_date) or _("New")

        return super().create(vals_list)
    
    def action_test(self):
        self.state = 'test'
    
    def action_approve(self):
        self.state = 'approved'

    def action_return(self):
        if self.state == 'test':
            self.state = 'draft'
        elif self.state == 'approved':
            self.state = 'test'

    @api.onchange('color_process_type_id','color_range_id','color_intensity_id')
    def _onchange_color_code(self):
        for rec in self:
            rec.color_code = (rec.color_process_type_id.code or '') + (rec.color_range_id.code or '') + (rec.color_intensity_id.code or '')

    @api.depends('color_process_type_id','color_range_id','color_intensity_id')
    def _compute_color_code(self):
        for rec in self:
            rec.color_code = (rec.color_process_type_id.code or '') + (rec.color_range_id.code or '') + (rec.color_intensity_id.code or '')