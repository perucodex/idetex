from odoo import models, fields, api

class ColorRecipeMixingGroup(models.Model):
    _name = 'color.recipe.mixing.group'
    _description = 'Color Recipe Mixing Group'

    name = fields.Char(string='Grupo', required=True)
    color_recipe_id = fields.Many2one('color.recipe', string='Receta de Color', ondelete='cascade')
    mixing_line_ids = fields.One2many('color.recipe.mixing.line', 'mixing_group_id', string='Lotes de Mezcla')
    lot_summary = fields.Char(string='Detalle de Lotes', compute='_compute_lot_summary')
    mixing_group_process_ids = fields.One2many('color.recipe.process', 'mixing_group_id', string='Procesos de Grupo')
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

    @api.depends('mixing_line_ids.lot_id.name')
    def _compute_lot_summary(self):
        for rec in self:
            rec.lot_summary = ', '.join(rec.mixing_line_ids.mapped('lot_id.name'))

    def action_view_group_recipe(self):
        self.ensure_one()
        if not self.mixing_group_process_ids and self.color_recipe_id:
            for process in self.color_recipe_id.color_recipe_process_ids:
                process.copy({
                    'color_recipe_id': False,
                    'stock_lot_id': False,
                    'mixing_group_id': self.id
                })
        if not self.colorfastness_washing_id:
            self.colorfastness_washing_id = self.env['colorfastness.washing'].create({})
        return {
            'name': f'Receta Grupo {self.name}',
            'type': 'ir.actions.act_window',
            'res_model': 'color.recipe.mixing.group',
            'res_id': self.id,
            'view_mode': 'form',
            'view_id': self.env.ref('idtx_laboratory.view_mixing_group_recipe_custom_form').id,
            'target': 'new',
        }

class ColorRecipeMixingLine(models.Model):
    _name = 'color.recipe.mixing.line'
    _description = 'Color Recipe Mixing Line'

    mixing_group_id = fields.Many2one('color.recipe.mixing.group', string='Grupo de Mezcla', ondelete='cascade')
    lot_id = fields.Many2one('stock.lot', string='Lote', required=True)
    product_id = fields.Many2one(related='lot_id.product_id', string='Producto', readonly=True)
    color_code = fields.Char(related='lot_id.color_code', string='Código de Color', readonly=True)
    color_name = fields.Char(related='lot_id.color_name', string='Nombre de Color', readonly=True)
    percentage = fields.Float(string='%', default=100.0)
