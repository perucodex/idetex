from odoo import models, fields, api, _, Command

class ColorRecipeProcess(models.Model):
    _name = 'color.recipe.process'
    _description = 'Color Recipe Process'

    sequence = fields.Integer('Sequence')
    color_recipe_id = fields.Many2one('color.recipe', string='Color Recipe', ondelete='cascade')
    stock_lot_id = fields.Many2one('stock.lot', string='Lot', ondelete='cascade')
    base_process_id = fields.Many2one('base.process', string='Process Template', ondelete='restrict')
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
    color_recipe_process_line_ids = fields.One2many('color.recipe.process.line', 'color_recipe_process_id', string='Color Process Line', copy=True)
    
    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for rec in records:
            if not rec.colorfastness_washing_id:
                rec.colorfastness_washing_id = self.env['colorfastness.washing'].create({})
        return records

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