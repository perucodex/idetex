from odoo import models, fields, api, _, Command

class ColorRecipeProcess(models.Model):
    _name = 'color.recipe.process'
    _description = 'Color Recipe Process'

    sequence = fields.Integer('Sequence')
    color_recipe_id = fields.Many2one('color.recipe', string='Color Recipe')
    color_recipe_process_template_id = fields.Many2one('color.recipe.process.template', string='Color Template')
    color_recipe_process_line_ids = fields.One2many('color.recipe.process.line', 'color_process_recipe_id', string='Color Process Line')

    @api.onchange('color_recipe_process_template_id')
    def _onchange_color_recipe_process_template_id(self):
        self.color_recipe_process_line_ids.unlink()
        self.color_recipe_process_line_ids = [Command.create({
            'color_process_recipe_id': self.id,
            'product_id': line.product_id.id,
            'factor': line.factor,
            'uom': line.uom,
            'quantity': 1,
        }) for line in self.color_recipe_process_template_id.color_recipe_process_template_line_ids]

class ColorRecipeProcessLine(models.Model):
    _name = 'color.recipe.process.line'
    _description = 'Color Recipe Process Line'

    color_process_recipe_id = fields.Many2one('color.recipe.process', string='Color Recipe Process')
    product_id = fields.Many2one('product.template', string='Product')
    factor = fields.Float('Factor', digits=(12,5))
    uom = fields.Selection([
        ('por', '%'),
        ('gxl', 'Gr/L'),
    ], string='Uom')
    quantity = fields.Float('Quantity', digits=(12,3))