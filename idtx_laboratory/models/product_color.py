from odoo import models, fields, api, _

class ProductColor(models.Model):
    _name = 'product.color'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Product Color'

    name = fields.Char('Name', tracking=True)
    recipe_ids = fields.One2many('color.recipe', 'product_color_id', string='Recipes')
    recipe_count = fields.Integer('Recipe Count', compute='_compute_recipe_count')

    def open_recipes(self):
        return self.recipe_ids._get_records_action(name=_("Recipes"))
    
    @api.depends('recipe_ids')
    def _compute_recipe_count(self):
        for rec in self:
            rec.recipe_count = len(rec.recipe_ids)