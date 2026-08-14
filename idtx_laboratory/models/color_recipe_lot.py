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
    # Búsqueda por texto del m2o (dropdown/Buscar más): por lotes, OF u opción.
    _rec_names_search = ['lot_summary', 'production_id.name',
                         'workorder_option_id.name']
    _order = 'id'

    color_recipe_id = fields.Many2one(
        'color.recipe', string='Receta de Color', required=True,
        ondelete='cascade', index=True)
    # La combinación de lotes ya no se digita: se toma de la OF. La OF tiene
    # una OT de tejido con OPCIONES (mrp.workorder.option) y cada opción lleva
    # sus líneas hilo+lote; al elegir OF y opción, los lotes se completan solos.
    production_id = fields.Many2one(
        'mrp.production', string='Orden de Fabricación', ondelete='set null',
        help='OF cuya OT de tejido tiene opciones con los lotes de hilo. '
             'Al elegir la opción, los lotes se completan automáticamente.')
    available_production_ids = fields.Many2many(
        'mrp.production', compute='_compute_available_productions',
        string='OFs Disponibles')
    workorder_option_id = fields.Many2one(
        'mrp.workorder.option', string='Opción', ondelete='set null',
        help='Opción de la OT de tejido de la OF; sus líneas hilo+lote '
             'definen la combinación de esta sub-receta.')
    available_option_ids = fields.Many2many(
        'mrp.workorder.option', compute='_compute_available_options',
        string='Opciones Disponibles')
    lot_ids = fields.Many2many(
        'stock.lot', 'color_recipe_lot_stock_lot_rel', 'recipe_lot_id', 'lot_id',
        string='Lotes de Hilo', required=True,
        domain="[('product_id.product_tmpl_id.is_thread', '=', True)]")
    lot_key = fields.Char(
        'Clave de Combinación', compute='_compute_lot_key', store=True, index=True,
        help='Identificador normalizado de la combinación (ids de lote '
             'ordenados). Permite buscar la combinación exacta desde las '
             'partidas.')
    # Almacenado para que el name_search del m2o (partida, Buscar más) pueda
    # buscar por el texto de los lotes.
    lot_summary = fields.Char('Lotes', compute='_compute_lot_summary', store=True)
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

    @api.depends('color_recipe_id.product_ids')
    def _compute_available_productions(self):
        """OFs elegibles: fabrican un producto de la receta y su OT de tejido
        tiene opciones (la OF se empareja con la receta por product_tmpl_id,
        igual que _compute_color_recipe de la OF)."""
        Option = self.env['mrp.workorder.option']
        for rec in self:
            templates = rec.color_recipe_id.product_ids
            if templates:
                options = Option.search([
                    ('workorder_id.operation_type', '=', 'weaving'),
                    ('workorder_id.production_id.state', '!=', 'cancel'),
                    ('workorder_id.production_id.product_id.product_tmpl_id',
                     'in', templates.ids),
                ])
                rec.available_production_ids = \
                    options.workorder_id.production_id
            else:
                # Sin productos en la receta no hay OF que emparejar.
                rec.available_production_ids = False

    @api.depends('production_id')
    def _compute_available_options(self):
        for rec in self:
            weaving_wos = rec.production_id.workorder_ids.filtered(
                lambda w: w.operation_type == 'weaving')
            rec.available_option_ids = weaving_wos.option_ids

    @api.onchange('production_id')
    def _onchange_production_id(self):
        for rec in self:
            if rec.workorder_option_id not in rec.available_option_ids:
                rec.workorder_option_id = False
            if not rec.workorder_option_id and len(rec.available_option_ids) == 1:
                rec.workorder_option_id = rec.available_option_ids
            rec._apply_option_lots()

    @api.onchange('workorder_option_id')
    def _onchange_workorder_option_id(self):
        self._apply_option_lots()

    def _apply_option_lots(self):
        """Vuelca los lotes de las líneas de la opción a la sub-receta."""
        for rec in self:
            if rec.workorder_option_id:
                rec.lot_ids = [(6, 0, rec.workorder_option_id.option_line_ids.lot_id.ids)]

    @api.depends('lot_summary', 'production_id.name', 'workorder_option_id.name',
                 'version')
    def _compute_display_name(self):
        # Varias sub-recetas pueden compartir la misma combinación de lotes
        # (una por opción de OF, y N versiones por opción): el nombre lleva la
        # OF/opción y la versión para distinguirlas, p.ej. al seleccionarla en
        # la partida. sudo: el nombre de la OF se lee saltando las reglas
        # multiempresa — sin él, a un usuario sin acceso a la compañía de la
        # OF le revienta cualquier pantalla que muestre la sub-receta.
        for rec in self:
            rec_s = rec.sudo()
            name = rec_s.lot_summary or _('(sin lotes)')
            if rec_s.production_id:
                option = ' · %s' % rec_s.workorder_option_id.name \
                    if rec_s.workorder_option_id.name else ''
                name = '%s (%s%s)' % (name, rec_s.production_id.name, option)
            if rec_s.version and rec_s.version > 1:
                name = '%s v%s' % (name, rec_s.version)
            rec.display_name = name

    state = fields.Selection([
        ('pending', 'Pendiente'),
        ('validated', 'Validada'),
        ('obsolete', 'Obsoleta'),
    ], string='Estado', default='pending', required=True)
    # Versionado tipo estampado (printing.design.rotary.line): se pueden
    # registrar N sub-recetas del MISMO hilo de versiones (misma opción de OF;
    # sin opción, misma combinación de lotes) sin restricción; al VALIDAR una,
    # las versiones anteriores del hilo quedan obsoletas.
    version = fields.Integer(
        'Versión', default=1, readonly=True, copy=False,
        help='Correlativo dentro del hilo de versiones (misma opción de OF; '
             'para filas sin opción, misma combinación de lotes). Al validar '
             'una versión, las anteriores quedan obsoletas.')

    # Una sub-receta VALIDADA u OBSOLETA es intocable: la validada se puede
    # reabrir (action_reset, grupo manager); la obsoleta es histórico.
    _PROTECTED_WHEN_VALIDATED = {'lot_ids', 'production_id', 'workorder_option_id',
                                 'absorption_factor', 'bath_ratio',
                                 'tipo_proceso', 'process_ids'}

    def write(self, vals):
        if self._PROTECTED_WHEN_VALIDATED & set(vals.keys()) \
                and 'state' not in vals:
            locked = self.filtered(lambda r: r.state in ('validated', 'obsolete'))
            if locked:
                raise UserError(_(
                    'La sub-receta %s está validada u obsoleta: no se puede '
                    'modificar (crea una nueva versión o reábrela).',
                    locked[0].display_name or locked[0].id))
        res = super().write(vals)
        # Si una fila PENDIENTE cambia de opción/lotes, cambia de hilo de
        # versiones: se le reasigna el correlativo del hilo nuevo.
        if {'workorder_option_id', 'lot_ids'} & set(vals):
            for rec in self.filtered(lambda r: r.state == 'pending'):
                rec.version = rec._next_version()
        return res

    def unlink(self):
        if any(r.state in ('validated', 'obsolete') for r in self):
            raise UserError(_(
                'No se puede eliminar una sub-receta validada u obsoleta: '
                'es el histórico de versiones.'))
        return super().unlink()

    def _version_group(self):
        """Hermanas del mismo hilo de versiones dentro de la receta: misma
        OPCIÓN de OF; para filas manuales (sin opción), misma combinación de
        lotes. No incluye a self."""
        self.ensure_one()
        siblings = self.color_recipe_id.recipe_lot_ids - self
        if self.workorder_option_id:
            return siblings.filtered(
                lambda r: r.workorder_option_id == self.workorder_option_id)
        return siblings.filtered(
            lambda r: not r.workorder_option_id and r.lot_key == self.lot_key)

    def _next_version(self):
        self.ensure_one()
        return max(self._version_group().mapped('version'), default=0) + 1

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for rec, vals in zip(records, vals_list):
            if not vals.get('version'):
                rec.version = rec._next_version()
        return records
    validated_date = fields.Date('Fecha Validación', readonly=True, copy=False)
    validated_by_id = fields.Many2one('res.users', 'Validada por', readonly=True, copy=False)
    # Relacionados ALMACENADOS de la receta madre: el menú "Recetas
    # Producción" lista las sub-recetas sueltas y necesita filtrar/agrupar
    # por cliente/color/compañía (read_group requiere columna en BD).
    partner_id = fields.Many2one(
        related='color_recipe_id.partner_id', string='Cliente', store=True)
    color_name = fields.Char(
        related='color_recipe_id.color_name', string='Nombre de Color',
        store=True)
    recipe_color_code = fields.Char(
        related='color_recipe_id.recipe_color_code',
        string='Código de Color', store=True)
    company_id = fields.Many2one(
        related='color_recipe_id.company_id', string='Compañía', store=True)
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
        'Factor de Absorción (L/kg)', digits=(12, 2), default=3.00,
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
            # El factor de la receta madre prima sobre el default del campo
            # (3.00); si la madre no tiene, se queda el default.
            if recipe and recipe.absorption_factor:
                rec.absorption_factor = recipe.absorption_factor
            if recipe and not rec.bath_ratio:
                rec.bath_ratio = recipe.bath_ratio

    # SIN restricción de unicidad: la misma opción de OF (y la misma
    # combinación de lotes) puede registrarse N veces; el versionado se
    # encarga de que solo una versión del hilo quede vigente al validar.

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
            if rec.state == 'obsolete':
                raise UserError(_(
                    'Una sub-receta obsoleta no se puede validar: crea una '
                    'nueva versión.'))
            if not rec.lot_ids:
                raise UserError(_('La sub-receta no tiene lotes de hilo.'))
            if rec.absorption_factor <= 0 or rec.bath_ratio <= 0:
                raise UserError(_(
                    'Para validar la sub-receta, el Factor de Absorción y la '
                    'Relación de Baño deben ser mayores a 0.'))
            # Al validar, las versiones ANTERIORES del mismo hilo quedan
            # obsoletas (las posteriores pendientes son borradores futuros).
            previous = rec._version_group().filtered(
                lambda r: r.version < rec.version and r.state != 'obsolete')
            if previous:
                previous.write({'state': 'obsolete'})
            rec.write({
                'state': 'validated',
                'validated_date': fields.Date.context_today(rec),
                'validated_by_id': rec.env.user.id,
            })

    def action_reset(self):
        for rec in self:
            if rec.state == 'obsolete':
                raise UserError(_(
                    'Una sub-receta obsoleta no se puede reabrir: la versión '
                    'vigente de su hilo es otra.'))
            group = rec._version_group()
            rec.write({
                'state': 'pending',
                'validated_date': False,
                'validated_by_id': False,
            })
            # Como en estampado: al reabrir la versión vigente se restaura la
            # última versión del hilo que estuvo validada (conserva su
            # validated_date histórico) y vuelven a pendiente los borradores
            # posteriores a ella que quedaron obsoletos.
            previous = group.filtered(
                lambda r: r.state == 'obsolete' and r.validated_date).sorted(
                key=lambda r: (r.version, r.id))
            if previous:
                restored = previous[-1]
                restored.write({'state': 'validated'})
                reopen = group.filtered(
                    lambda r: r.state == 'obsolete' and not r.validated_date
                    and r.version > restored.version)
                if reopen:
                    reopen.write({'state': 'pending'})
