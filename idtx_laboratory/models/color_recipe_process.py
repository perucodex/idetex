from odoo import models, fields, api, _, Command

class ColorRecipeProcess(models.Model):
    _name = 'color.recipe.process'
    _description = 'Color Recipe Process'

    sequence = fields.Integer('Sequence')
    color_recipe_id = fields.Many2one('color.recipe', string='Color Recipe', ondelete='cascade')
    stock_lot_id = fields.Many2one('stock.lot', string='Lot', ondelete='cascade')
    base_process_id = fields.Many2one('base.process', string='Process Template', ondelete='restrict')
    color_recipe_process_line_ids = fields.One2many('color.recipe.process.line', 'color_recipe_process_id', string='Color Process Line', copy=True)

    @api.onchange('base_process_id')
    def _onchange_base_process_id(self):
        if not self.base_process_id:
            self.color_recipe_process_line_ids = [Command.clear()]
            return
        commands = [Command.clear()]
        commands += [
            Command.create({
                'product_id': line.product_id.id,
                'factor': line.factor,
                'uom': line.uom,
            })
            for line in self.base_process_id.base_process_line_ids
        ]
        self.color_recipe_process_line_ids = commands

class ColorRecipeProcessLine(models.Model):
    _name = 'color.recipe.process.line'
    _description = 'Color Recipe Process Line'

    color_recipe_process_id = fields.Many2one('color.recipe.process', string='Color Recipe Process', ondelete='cascade')
    color_recipe_state = fields.Selection(related='color_recipe_process_id.color_recipe_id.state')
    product_id = fields.Many2one('product.template', string='Product', ondelete='restrict')
    factor = fields.Float('Factor', digits=(12,5))
    uom = fields.Selection([
        ('por', '%'),
        ('gxl', 'Gr/L'),
    ], string='Uom', default='gxl')
    # quantity = fields.Float('Quantity', digits=(12,3))