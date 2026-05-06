from odoo import models, fields, api, _
from odoo.exceptions import UserError

class ColorRecipe(models.Model):
    _name = 'color.recipe'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Color Recipe'

    name = fields.Char('Name', copy=False, default=lambda self: _('New'))
    lab_dev_line_id = fields.Many2one('lab.dev.line', string='Lab Dev Line', ondelete='cascade')
    lab_dev_id = fields.Many2one(related='lab_dev_line_id.lab_dev_id')
    product_id = fields.Many2one(related='lab_dev_line_id.product_id')
    color_code = fields.Char(related='lab_dev_line_id.color_code')
    color_name = fields.Char(related='lab_dev_line_id.color_name')
    partner_id = fields.Many2one(related='lab_dev_id.partner_id')
    recipe_date = fields.Date('Recipe Date', default=fields.Date.context_today, copy=False)
    color_recipe_process_ids = fields.One2many('color.recipe.process', 'color_recipe_id', string='Color Recipe Process', copy=True)
    lot_ids = fields.One2many('stock.lot', 'color_recipe_id', string='Lotes')
    # color = fields.Char('Color')
    recipe_color_code = fields.Char('Recipe Color Code', readonly=True, copy=False)
    # last_color_code = fields.Char('Last Color Code')
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
        index=True,
        required=True
    )
    state = fields.Selection([
        ('test', 'Test'),
        ('approved', 'Approved'),
    ], string='State', default='test', tracking=True)
    
    #=== CRUD METHODS ===#

    @api.model_create_multi
    def create(self, vals_list):
        counter = 0
        for vals in vals_list:
            if vals.get('name', _("New")) == _("New"):
                seq_date = fields.Datetime.context_timestamp(
                    self, fields.Datetime.to_datetime(vals['recipe_date'])
                ) if 'recipe_date' in vals else None
                vals['name'] = self.env['ir.sequence'].with_company(vals.get('company_id')).next_by_code(
                    'color.recipe', sequence_date=seq_date) or _("New")
        
            lab_dev_line_id = vals.get('lab_dev_line_id')
            if lab_dev_line_id:
                line = self.env['lab.dev.line'].browse(lab_dev_line_id)
                prefix = line.color_code or ''
                if prefix:
                    # Buscar el último recipe_color_code que empiece con ese prefijo
                    existing = self.search([
                        ('lab_dev_line_id', '=', lab_dev_line_id),
                        ('recipe_color_code', 'ilike', f'{prefix}-%')
                    ], order='recipe_color_code desc', limit=1)

                    last_number = 0
                    if existing:
                        try:
                            last_number = int(existing.recipe_color_code.split('-')[-1])
                        except Exception:
                            last_number = 0

                    new_suffix = str(last_number + 1 + counter).zfill(3)
                    vals['recipe_color_code'] = f'{prefix}-{new_suffix}'
                    counter += 1

        return super().create(vals_list)
    
    def action_approve(self):
        if any(cr.state == 'approved' for cr in self.lab_dev_line_id.color_recipe_ids.filtered(lambda cr: cr.color_name == self.color_name)):
            raise UserError(_('You can\'t approve this recipe. Another recipe in the Lab Dev for color %s is already approved.') %self.lab_dev_line_id.color_name)
        self.state = 'approved'
        self.lab_dev_line_id.state = 'approved'

    def action_return(self):
        self.state = 'test'
        self.lab_dev_line_id.state = self.state

    def action_adjust_recipe(self):
        self.ensure_one()
        new_recipe = self.copy()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Adjusted Recipe',
            'view_mode': 'form',
            'res_model': self._name,
            'res_id': new_recipe.id,
            'target': 'current',
        }

    def unlink(self):
        for rec in self:
            if rec.state == 'approved':
                raise UserError(_('Can\'t delete a recipe in approved state.'))
        return super().unlink()