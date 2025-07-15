from odoo import models, fields, api, _

class ColorRecipeProcessTemplate(models.Model):
    _name = 'color.recipe.process.template'
    _description = 'Color Recipe Process'

    sequence = fields.Integer('Sequence')
    color_recipe_id = fields.Many2one('color.recipe', string='Color Recipe')
    name = fields.Char('Name')
    code = fields.Char('Code')
    nc = fields.Integer('Nc')
    lin_maq = fields.Integer('Lin. Maq.')
    codmaq = fields.Char('Código de Máquina')
    color_recipe_process_template_line_ids = fields.One2many('color.recipe.process.template.line', 'color_recipe_process_template_id', string='Color Process Line')

class ColorRecipeProcessTemplateLine(models.Model):
    _name = 'color.recipe.process.template.line'
    _description = 'Color Recipe Process'

    color_recipe_process_template_id = fields.Many2one('color.recipe.process.template', string='Color Recipe Process Template')
    product_id = fields.Many2one('product.template', string='Product')
    factor = fields.Float('Factor', digits=(12,5))
    # uom_id = fields.Many2one('uom.uom', string='Uom')
    uom = fields.Selection([
        ('por', '%'),
        ('gxl', 'Gr/L'),
    ], string='Uom')
