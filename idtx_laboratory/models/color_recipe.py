from odoo import models, fields, api, _
from odoo.exceptions import UserError

class ColorRecipe(models.Model):
    _name = 'color.recipe'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Color Recipe'

    name = fields.Char('Name', copy=False, default=lambda self: _('New'))
    lab_dev_line_id = fields.Many2one('lab.dev.line', string='Lab Dev Line', ondelete='cascade')
    lab_dev_id = fields.Many2one(related='lab_dev_line_id.lab_dev_id')
    product_ids = fields.Many2many(related='lab_dev_line_id.product_ids')
    product_id = fields.Many2one(
        'product.template', string='Product', ondelete='restrict',
        domain="[('id', 'in', product_ids)]")
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
    colorfastness_washing_id = fields.Many2one('colorfastness.washing', string='Solidez al Lavado', ondelete='cascade')
    
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
    state = fields.Selection([
        ('test', 'Test'),
        ('approved', 'Approved'),
    ], string='State', default='test', tracking=True)
    observations = fields.Text('Observaciones')
    mixing_group_ids = fields.One2many('color.recipe.mixing.group', 'color_recipe_id', string='Grupos de Mezcla')
    
    #=== CRUD METHODS ===#

    @api.model_create_multi
    def create(self, vals_list):
        # Números ya usados por línea de lab dev (para reutilizar huecos).
        used_by_line = {}
        for vals in vals_list:
            # La receta hereda la empresa de su Lab Dev (puede ser la empresa
            # productiva), de modo que la secuencia y el registro queden en
            # la empresa correcta.
            if vals.get('lab_dev_line_id') and not vals.get('company_id'):
                lab_dev = self.env['lab.dev.line'].browse(vals['lab_dev_line_id']).lab_dev_id
                if lab_dev.company_id:
                    vals['company_id'] = lab_dev.company_id.id

            if vals.get('name', _("New")) == _("New"):
                seq_date = fields.Datetime.context_timestamp(
                    self, fields.Datetime.to_datetime(vals['recipe_date'])
                ) if 'recipe_date' in vals else None
                vals['name'] = self.env['ir.sequence'].with_company(vals.get('company_id')).next_by_code(
                    'color.recipe', sequence_date=seq_date) or _("New")

            lab_dev_line_id = vals.get('lab_dev_line_id')
            if lab_dev_line_id and not vals.get('recipe_color_code'):
                line = self.env['lab.dev.line'].browse(lab_dev_line_id)
                prefix = line.color_code or ''
                if prefix:
                    # Recolecta los correlativos ya en uso para esta línea
                    # (una sola vez por línea dentro de este lote de creación).
                    if lab_dev_line_id not in used_by_line:
                        used = set()
                        for rec in line.color_recipe_ids:
                            code = rec.recipe_color_code or ''
                            if code.startswith(f'{prefix}-'):
                                try:
                                    used.add(int(code.rsplit('-', 1)[-1]))
                                except ValueError:
                                    pass
                        used_by_line[lab_dev_line_id] = used
                    used = used_by_line[lab_dev_line_id]

                    # Toma el menor correlativo libre (reutiliza huecos).
                    n = 1
                    while n in used:
                        n += 1
                    used.add(n)
                    vals['recipe_color_code'] = f'{prefix}-{str(n).zfill(3)}'

        records = super().create(vals_list)
        for rec in records:
            if not rec.colorfastness_washing_id:
                rec.colorfastness_washing_id = self.env['colorfastness.washing'].create({})
        return records
    
    def action_approve(self):
        if any(cr.state == 'approved'
               for cr in self.lab_dev_line_id.color_recipe_ids.filtered(
                   lambda cr: cr.color_name == self.color_name and cr.product_id == self.product_id)):
            raise UserError(_(
                'You can\'t approve this recipe. Another recipe in the Lab Dev for product %(product)s and color %(color)s is already approved.',
                product=self.product_id.display_name or _('N/A'),
                color=self.color_name,
            ))
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