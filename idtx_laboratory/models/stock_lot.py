from odoo import api, fields, models

class StockLot(models.Model):
    _inherit = 'stock.lot'

    color_recipe_id = fields.Many2one('color.recipe', string='Color Recipe')
    color_code = fields.Char(related='color_recipe_id.color_code')
    color_name = fields.Char(related='color_recipe_id.color_name')
    color_recipe_process_ids = fields.One2many('color.recipe.process', 'stock_lot_id', string='Procesos de Lote')
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
    recipe_lot_title = fields.Char(string='Título Receta Lote', compute='_compute_recipe_lot_title')

    @api.depends('color_recipe_id.lab_dev_id.name', 'name')
    def _compute_recipe_lot_title(self):
        for rec in self:
            ld_name = rec.color_recipe_id.lab_dev_id.name if rec.color_recipe_id and rec.color_recipe_id.lab_dev_id else ''
            rec.recipe_lot_title = f"Receta {ld_name} + {rec.name}"

    def action_view_lot_recipe(self):
        self.ensure_one()
        
        # Lazy copy of recipe processes
        if not self.color_recipe_process_ids and self.color_recipe_id:
            for process in self.color_recipe_id.color_recipe_process_ids:
                process.copy({
                    'color_recipe_id': False,
                    'stock_lot_id': self.id
                })
        
        if not self.colorfastness_washing_id:
            self.colorfastness_washing_id = self.env['colorfastness.washing'].create({})
                
        view_id = self.env.ref('idtx_laboratory.view_stock_lot_recipe_custom_form').id
        return {
            'name': 'Receta de Lote',
            'type': 'ir.actions.act_window',
            'res_model': 'stock.lot',
            'res_id': self.id,
            'view_mode': 'form',
            'view_id': view_id,
            'target': 'new',
        }