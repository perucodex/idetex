import base64

from odoo import models, fields, api, _
from odoo.exceptions import UserError
from odoo.tools import file_path


class ColorRecipeLot(models.Model):
    """Sub-receta por combinación de lotes de hilo.

    Una receta de color se desarrolla con una muestra tejida con una
    combinación concreta de lotes de hilado (1..N lotes). Cuando producción
    trabaja con otra combinación, laboratorio la valida y queda registrada
    aquí, con su propia solidez al lavado. Reemplaza a los antiguos
    color.recipe.mixing.group y a las "recetas por lote" sobre stock.lot.
    """
    _name = 'color.recipe.lot'
    _description = 'Sub-receta por combinación de lotes'
    _rec_name = 'lot_summary'
    _order = 'id'

    color_recipe_id = fields.Many2one(
        'color.recipe', string='Receta de Color', required=True,
        ondelete='cascade', index=True)
    lot_ids = fields.Many2many(
        'stock.lot', 'color_recipe_lot_stock_lot_rel', 'recipe_lot_id', 'lot_id',
        string='Lotes de Hilo', required=True,
        domain="[('product_id.product_tmpl_id.is_thread', '=', True)]")
    lot_key = fields.Char(
        'Clave de Combinación', compute='_compute_lot_key', store=True, index=True,
        help='Identificador normalizado de la combinación (ids de lote '
             'ordenados). Permite buscar la combinación exacta desde las '
             'partidas.')
    lot_summary = fields.Char('Lotes', compute='_compute_lot_summary')
    # Lotes elegibles: solo los de los hilos que consumen las LdM de los
    # productos de la receta. Evita elegir un lote homónimo de otro hilo
    # (pueden existir varios lotes llamados "123" de hilos distintos).
    available_thread_lot_ids = fields.Many2many(
        'stock.lot', compute='_compute_available_thread_lots',
        string='Lotes Disponibles')

    @api.depends('color_recipe_id.product_ids')
    def _compute_available_thread_lots(self):
        Lot = self.env['stock.lot']
        for rec in self:
            threads = rec.color_recipe_id.product_ids.bom_ids.bom_line_ids.mapped(
                'product_id').filtered(lambda p: p.is_thread)
            if threads:
                rec.available_thread_lot_ids = Lot.search(
                    [('product_id', 'in', threads.ids)])
            else:
                # Sin LdM conocida: cualquier lote de hilo.
                rec.available_thread_lot_ids = Lot.search(
                    [('product_id.product_tmpl_id.is_thread', '=', True)])
    state = fields.Selection([
        ('pending', 'Pendiente'),
        ('validated', 'Validada'),
    ], string='Estado', default='pending', required=True)
    validated_date = fields.Date('Fecha Validación', readonly=True, copy=False)
    validated_by_id = fields.Many2one('res.users', 'Validada por', readonly=True, copy=False)
    # Procesos propios de la combinación: los factores pueden variar según
    # el hilado. Se copian de la receta madre al abrir la sub-receta por
    # primera vez (copia perezosa) y ahí se ajustan.
    process_ids = fields.One2many(
        'color.recipe.process', 'recipe_lot_id', string='Procesos')

    # Nota: la solidez al lavado NO vive aquí — es inherente al COLOR
    # (lab.dev.line). La sub-receta registra la combinación de lotes, sus
    # procesos con factores ajustados por hilado y la validación.

    # Parámetros de teñido de la combinación (por defecto heredan los de la
    # receta madre; cada combinación puede ajustarlos).
    absorption_factor = fields.Float(
        'Factor de Absorción (L/kg)', digits=(12, 2),
        help='Litros de baño absorbidos por kilogramo de tela.')
    bath_ratio = fields.Integer(
        'Relación de Baño 1:',
        help='Relación de baño 1:N en litros por kilogramo. '
             'Ej.: ingrese 10 para una relación 1:10 (uno a diez).')
    # Mismo catálogo de curvas que batch.registry (tipo_proceso); la imagen
    # de la curva vive en idtx_mrp_shop/static/src/images/<tipo>.jpg.
    tipo_proceso = fields.Selection([
        ('ISOTERMICA60', 'ISOTERMICA60'),
        ('MIGRACION40-60', 'MIGRACION40-60'),
        ('MIGRACION60-80-60', 'MIGRACION60-80-60'),
        ('MIGRACION80-90-60', 'MIGRACION80-90-60'),
        ('MIGRASALADE160-80-60', 'MIGRASALADE160-80-60'),
    ], string='Tipo de Proceso')
    imagen_proceso = fields.Binary(
        'Imagen Proceso', compute='_compute_imagen_proceso', store=False)

    @api.depends('tipo_proceso')
    def _compute_imagen_proceso(self):
        for rec in self:
            rec.imagen_proceso = False
            if rec.tipo_proceso:
                try:
                    path = file_path(
                        f'idtx_mrp_shop/static/src/images/{rec.tipo_proceso}.jpg')
                    with open(path, 'rb') as f:
                        rec.imagen_proceso = base64.b64encode(f.read())
                except (FileNotFoundError, OSError):
                    pass

    @api.onchange('color_recipe_id')
    def _onchange_recipe_defaults(self):
        for rec in self:
            recipe = rec.color_recipe_id
            if recipe and not rec.absorption_factor:
                rec.absorption_factor = recipe.absorption_factor
            if recipe and not rec.bath_ratio:
                rec.bath_ratio = recipe.bath_ratio

    _lot_combination_unique = models.Constraint(
        'unique(color_recipe_id, lot_key)',
        'Esta combinación de lotes ya está registrada en la receta.',
    )

    @staticmethod
    def _make_lot_key(lot_ids):
        """Clave canónica de una combinación de lotes (ids ordenados)."""
        return '-'.join(str(i) for i in sorted(set(lot_ids)))

    @api.depends('lot_ids')
    def _compute_lot_key(self):
        for rec in self:
            rec.lot_key = self._make_lot_key(rec.lot_ids.ids) if rec.lot_ids else False

    @api.depends('lot_ids.name')
    def _compute_lot_summary(self):
        for rec in self:
            rec.lot_summary = ', '.join(rec.lot_ids.mapped('name'))

    def action_open_subrecipe(self):
        """Abre la sub-receta en formulario. La primera vez copia los
        procesos (con sus líneas y factores) de la receta madre para poder
        ajustar las dosificaciones según el hilado."""
        self.ensure_one()
        if not self.process_ids and self.color_recipe_id.color_recipe_process_ids:
            for process in self.color_recipe_id.color_recipe_process_ids:
                process.copy({
                    'color_recipe_id': False,
                    'stock_lot_id': False,
                    'mixing_group_id': False,
                    'colorfastness_washing_id': False,
                    'recipe_lot_id': self.id,
                })
        return {
            'name': _('Sub-receta %s') % (self.lot_summary or ''),
            'type': 'ir.actions.act_window',
            'res_model': 'color.recipe.lot',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_validate(self):
        for rec in self:
            if not rec.lot_ids:
                raise UserError(_('La sub-receta no tiene lotes de hilo.'))
            rec.write({
                'state': 'validated',
                'validated_date': fields.Date.context_today(rec),
                'validated_by_id': rec.env.user.id,
            })

    def action_reset(self):
        self.write({
            'state': 'pending',
            'validated_date': False,
            'validated_by_id': False,
        })
