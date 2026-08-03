from odoo import models, fields, api, _, Command
from odoo.exceptions import UserError

class ColorRecipeProcess(models.Model):
    _name = 'color.recipe.process'
    _description = 'Color Recipe Process'

    sequence = fields.Integer('Sequence')
    color_recipe_id = fields.Many2one('color.recipe', string='Color Recipe', ondelete='cascade')
    # Legacy (sin UI): stock_lot_id y mixing_group_id eran los antiguos
    # flujos de receta por lote; el vigente es recipe_lot_id (sub-receta).
    stock_lot_id = fields.Many2one('stock.lot', string='Lot', ondelete='cascade')
    mixing_group_id = fields.Many2one('color.recipe.mixing.group', string='Mixing Group', ondelete='cascade')
    recipe_lot_id = fields.Many2one('color.recipe.lot', string='Sub-receta por Lote', ondelete='cascade')
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
    
    # Nota: ya no se auto-crea colorfastness.washing por proceso — la solidez
    # vive en la sub-receta por combinación de lotes (color.recipe.lot).

    @api.onchange('base_process_id')
    def _onchange_base_process_id(self):
        if not self.base_process_id:
            self.color_recipe_process_line_ids = [Command.clear()]
            return
        commands = [Command.clear()]
        commands += [
            Command.create({
                'line_type': line.line_type,
                'product_id': line.product_id.id,
                'factor': line.factor,
                'uom': line.uom,
                'order_number': line.order_number,
                'sequence': line.sequence,
                'base_line_id': line.id,
            })
            for line in self.base_process_id.base_process_line_ids
        ]
        self.color_recipe_process_line_ids = commands

    def _resequence_lines(self):
        """Normaliza la secuencia (la lista con handle ordena SOLO por
        secuencia): el N° siempre manda; dentro del N° vale el arrastre."""
        for proc in self:
            lines = proc.color_recipe_process_line_ids.sorted(
                key=lambda l: (l.order_number or 0, l.sequence, l.id))
            for i, line in enumerate(lines):
                seq = (i + 1) * 10
                if line.sequence != seq:
                    line.with_context(skip_reseq=True).sequence = seq

class ColorRecipeProcessLine(models.Model):
    _name = 'color.recipe.process.line'
    _description = 'Color Recipe Process Line'
    # El N° manda: el handle solo reordena DENTRO del grupo de su N°.
    _order = 'order_number, sequence, id'

    sequence = fields.Integer('Secuencia', default=10)
    color_recipe_process_id = fields.Many2one('color.recipe.process', string='Color Recipe Process', ondelete='cascade')
    color_recipe_state = fields.Selection(related='color_recipe_process_id.color_recipe_id.state')
    recipe_lot_state = fields.Selection(related='color_recipe_process_id.recipe_lot_id.state')
    # Linea 'colorants' = hueco de COLORANTES heredado del proceso base: el
    # laboratorio elige ahi los productos REALES (marca concreta) como
    # SUB-LINEAS (child_ids). Las sub-lineas cuelgan solo del padre (sin
    # color_recipe_process_id) para no duplicarse en la lista del proceso.
    line_type = fields.Selection([
        ('product', 'Producto'),
        ('colorants', 'Colorantes'),
        ('range', 'Tabla'),
    ], string='Tipo', default='product', required=True)
    parent_line_id = fields.Many2one('color.recipe.process.line', string='Línea Padre', ondelete='cascade')
    child_ids = fields.One2many('color.recipe.process.line', 'parent_line_id',
                                string='Colorantes', copy=True)
    product_id = fields.Many2one('product.template', string='Product', ondelete='restrict')
    factor = fields.Float('Factor', digits=(12,5))
    # N° de orden de ingreso a maquina (heredado del proceso base; en el
    # reporte de receta la numeracion se acumula entre procesos).
    order_number = fields.Integer('N°', default=1)
    uom = fields.Selection([
        ('por', '%'),
        ('gxl', 'Gr/L'),
    ], string='Uom', default='gxl')
    # quantity = fields.Float('Quantity', digits=(12,3))
    # Producto con TABLA: enlaza a la línea del proceso base cuyos rangos
    # (CF -> cantidad) resuelven el factor. CF = suma de % de los COLORANTES
    # del MISMO proceso; al cambiar los %, el factor se recalcula salvo
    # ajuste manual del laboratorista (factor_manual).
    base_line_id = fields.Many2one('base.process.line', string='Línea Base', ondelete='set null')
    has_table = fields.Boolean(related='base_line_id.has_table')
    factor_manual = fields.Boolean(
        'Ajuste Manual', default=False,
        help='El factor fue corregido a mano: el recálculo por tabla no lo pisa.')

    @api.depends('line_type', 'product_id', 'child_ids.product_id', 'child_ids.factor')
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = 'COLORANTES' if rec.line_type == 'colorants' \
                else (rec.product_id.display_name or _('Línea'))

    def _get_processes(self):
        """Proceso dueño: directo o a través de la línea padre (sub-líneas)."""
        return self.color_recipe_process_id | self.parent_line_id.color_recipe_process_id

    # ------------------------------------------------------------------
    # Motor de tablas (CF)
    # ------------------------------------------------------------------
    def _recompute_table_factors(self):
        """Recalcula el factor de las líneas CON TABLA de los procesos de
        `self`: CF = suma de % de las líneas de COLORANTES del mismo
        proceso (incluye las sub-líneas del hueco COLORANTES); se busca el
        rango que contiene el CF y se toma su cantidad. Las líneas con
        ajuste manual no se tocan."""
        for process in self._get_processes():
            lines = process.color_recipe_process_line_ids
            all_lines = lines | lines.child_ids
            cf = sum(l.factor for l in all_lines
                     if l.uom == 'por' and l.product_id.is_colorant)
            for tl in lines.filtered(lambda l: l.base_line_id.range_ids and not l.factor_manual):
                rng = tl.base_line_id.range_ids.filtered(
                    lambda r: r.percent_from <= cf <= r.percent_to)[:1]
                if rng and tl.factor != rng.factor:
                    tl.with_context(table_recompute=True).factor = rng.factor

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        if not self.env.context.get('table_recompute'):
            records._recompute_table_factors()
        if not self.env.context.get('skip_reseq'):
            records.color_recipe_process_id._resequence_lines()
        return records

    def write(self, vals):
        # Editar a mano el factor de una línea con tabla la marca como manual.
        if 'factor' in vals and not self.env.context.get('table_recompute') \
                and 'factor_manual' not in vals:
            manual = self.filtered(lambda l: l.base_line_id.range_ids)
            if manual:
                super(ColorRecipeProcessLine, manual).write({'factor_manual': True})
        res = super().write(vals)
        if not self.env.context.get('table_recompute') \
                and ({'factor', 'uom', 'product_id'} & set(vals.keys())):
            self._recompute_table_factors()
        if not self.env.context.get('skip_reseq') \
                and ({'sequence', 'order_number'} & set(vals.keys())):
            self.color_recipe_process_id._resequence_lines()
        return res

    def unlink(self):
        processes = self._get_processes()
        res = super().unlink()
        processes.color_recipe_process_line_ids._recompute_table_factors()
        return res

    def action_reset_table_factor(self):
        """Quita el ajuste manual y vuelve al valor de la tabla."""
        if any(l.recipe_lot_state in ('validated', 'obsolete') for l in self):
            raise UserError(_('La sub-receta está validada u obsoleta: no se '
                              'pueden modificar sus factores.'))
        self.write({'factor_manual': False})
        self._recompute_table_factors()