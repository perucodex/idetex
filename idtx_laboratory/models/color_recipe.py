from odoo import models, fields, api, _

class ColorRecipe(models.Model):
    _name = 'color.recipe'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Color Recipe'

    product_color_id = fields.Many2one('product.color', 'Product Color')
    name = fields.Char('Name', copy=False, default=lambda self: _('New'))
    recipe_date = fields.Date('Recipe Date', default=fields.Date.context_today, copy=False)
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