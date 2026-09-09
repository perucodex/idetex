from markupsafe import Markup

from odoo import models, fields, api, _, Command
from odoo.exceptions import UserError


# ----------------------------------------------------------------------
# Bitácora de la receta (color.recipe) y de la sub-receta (color.recipe.lot)
# ----------------------------------------------------------------------
# Cada alta/baja/cambio de un proceso o de una línea se ENCOLA aquí y al
# precommit se publica UNA nota por receta/sub-receta con todos los cambios
# de la transacción: un guardado del form (que dispara N writes de líneas)
# = un solo mensaje en el chatter. El dueño del proceso (madre o sub-receta)
# lo resuelve color.recipe.process._log_owner().
_LOG_KEY = 'idtx_recipe_log'


def _queue_recipe_log(env, owners, entry):
    """Encola `entry` (str o Markup) en la bitácora de los `owners`
    (recetas color.recipe y/o sub-recetas color.recipe.lot). Se omite con el
    contexto skip_recipe_log (copias de procesos entre recetas, creación de
    un proceso con sus líneas)."""
    owners = [o for o in owners if o]
    if not owners or env.context.get('skip_recipe_log'):
        return
    data = env.cr.precommit.data
    if _LOG_KEY not in data:
        data[_LOG_KEY] = {}
        env.cr.precommit.add(lambda: _flush_recipe_log(env))
    for owner in owners:
        data[_LOG_KEY].setdefault((owner._name, owner.id), []).append(entry)


def _flush_recipe_log(env):
    pending = env.cr.precommit.data.pop(_LOG_KEY, None) or {}
    for (model, res_id), entries in pending.items():
        owner = env[model].browse(res_id).exists()
        if not owner:
            continue
        items = Markup('').join(Markup('<li>%s</li>') % e for e in entries)
        owner._message_log(body=Markup('<p>%s</p><ul>%s</ul>') % (
            _('Cambios en la receta:'), items))


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

    # ---- bitácora (receta madre o sub-receta) ----
    def _log_owner(self):
        """Dueño con chatter del proceso: la sub-receta si es de producción,
        si no la receta madre; vacío en los flujos legacy (lote/mixing)."""
        self.ensure_one()
        return self.recipe_lot_id or self.color_recipe_id

    def _log_name(self):
        self.ensure_one()
        return self.base_process_id.display_name or _('Proceso')

    @api.model_create_multi
    def create(self, vals_list):
        # Las líneas nacen con el proceso: se registra el proceso completo
        # (no línea por línea), por eso las líneas se crean con el skip.
        # with_env: los registros devueltos NO deben arrastrar el skip (si no,
        # un unlink/write posterior sobre ellos tampoco se registraría).
        records = super(ColorRecipeProcess,
                        self.with_context(skip_recipe_log=True)).create(vals_list)
        records = records.with_env(self.env)
        for rec in records:
            _queue_recipe_log(self.env, [rec._log_owner()], _(
                'Proceso agregado: %(process)s (%(count)s líneas)',
                process=rec._log_name(),
                count=len(rec.color_recipe_process_line_ids)))
        return records

    def write(self, vals):
        before = {rec.id: rec._log_name() for rec in self} \
            if 'base_process_id' in vals else None
        res = super().write(vals)
        if before is not None:
            for rec in self:
                if rec._log_name() != before[rec.id]:
                    _queue_recipe_log(self.env, [rec._log_owner()], _(
                        'Proceso cambiado: %(old)s → %(new)s',
                        old=before[rec.id], new=rec._log_name()))
        return res

    def unlink(self):
        for rec in self:
            _queue_recipe_log(self.env, [rec._log_owner()], _(
                'Proceso eliminado: %(process)s (%(count)s líneas)',
                process=rec._log_name(),
                count=len(rec.color_recipe_process_line_ids)))
        return super().unlink()

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

    def _sibling_processes(self):
        """Procesos de la misma receta (madre o sub-receta), incluido self."""
        self.ensure_one()
        if self.recipe_lot_id:
            return self.recipe_lot_id.process_ids
        if self.color_recipe_id:
            return self.color_recipe_id.color_recipe_process_ids
        return self

    def _cf_sum(self):
        """CF del conjunto de procesos `self`: suma de % de las líneas cuyo
        producto es colorante (incluye las sub-líneas del hueco COLORANTES)."""
        lines = self.color_recipe_process_line_ids
        all_lines = lines | lines.child_ids
        return sum(l.factor for l in all_lines
                   if l.uom == 'por' and l.product_id.is_colorant)

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
    # Solo insumos de laboratorio: is_chemical es el flag paraguas (lo llevan
    # tambien los colorantes y auxiliares), el mismo dominio del menu Quimicos.
    product_id = fields.Many2one(
        'product.template', string='Product', ondelete='restrict',
        domain=[('is_chemical', '=', True)])
    factor = fields.Float('Factor', digits=(12,5))
    # N° de orden de ingreso a maquina (heredado del proceso base; en el
    # reporte de receta la numeracion se acumula entre procesos).
    order_number = fields.Integer('N°', default=1)
    uom = fields.Selection([
        ('por', '%'),
        ('gxl', 'Gr/L'),
    ], string='Uom', default='gxl')
    # Lote del insumo (químicos/colorantes con seguimiento por lote): solo se
    # registra en las sub-recetas de producción (recipe_lot_id), donde importa
    # la partida real del producto usada; la receta desarrollo no lleva lote.
    lot_id = fields.Many2one(
        'stock.lot', string='Lote', ondelete='restrict',
        domain="[('product_id.product_tmpl_id', '=', product_id)]")
    product_tracking = fields.Selection(related='product_id.tracking')
    is_subrecipe_line = fields.Boolean(compute='_compute_is_subrecipe_line')
    # Semáforo de calificación del lote (widget state_selection): verde si el
    # lote está validado por laboratorio, rojo si no; sin lote no se muestra.
    lot_qualification = fields.Selection([
        ('blocked', 'Lote NO validado'),
        ('done', 'Lote validado'),
    ], compute='_compute_lot_qualification')

    @api.depends('lot_id.lab_state')
    def _compute_lot_qualification(self):
        for rec in self:
            if not rec.lot_id:
                rec.lot_qualification = False
            else:
                rec.lot_qualification = 'done' \
                    if rec.lot_id.lab_state == 'validated' else 'blocked'
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

    @api.depends('color_recipe_process_id.recipe_lot_id',
                 'parent_line_id.color_recipe_process_id.recipe_lot_id')
    def _compute_is_subrecipe_line(self):
        # Las sub-líneas de COLORANTES no llevan color_recipe_process_id:
        # heredan el contexto (receta madre vs sub-receta) de su línea padre.
        for rec in self:
            process = rec.color_recipe_process_id \
                or rec.parent_line_id.color_recipe_process_id
            rec.is_subrecipe_line = bool(process.recipe_lot_id)

    @api.onchange('product_id')
    def _onchange_product_id_clear_lot(self):
        for rec in self:
            if rec.lot_id and rec.lot_id.product_id.product_tmpl_id != rec.product_id:
                rec.lot_id = False

    def _get_processes(self):
        """Proceso dueño: directo o a través de la línea padre (sub-líneas)."""
        return self.color_recipe_process_id | self.parent_line_id.color_recipe_process_id

    # ------------------------------------------------------------------
    # Bitácora de la receta / sub-receta (ver _queue_recipe_log)
    # ------------------------------------------------------------------
    # Campos cuyo cambio se registra (la secuencia del arrastre no: la
    # normaliza _resequence_lines y solo hace ruido).
    _LOGGED_FIELDS = ('line_type', 'product_id', 'lot_id', 'order_number',
                      'factor', 'uom', 'factor_manual')

    def _log_owners(self):
        return [p._log_owner() for p in self._get_processes()]

    def _log_value(self, fname):
        """Valor legible del campo para la bitácora."""
        self.ensure_one()
        field = self._fields[fname]
        value = self[fname]
        if field.type == 'many2one':
            return value.display_name or '—'
        if field.type == 'selection':
            return dict(field._description_selection(self.env)).get(value) or '—'
        if field.type == 'boolean':
            return _('Sí') if value else _('No')
        if field.type == 'float':
            digits = field.get_digits(self.env)
            return '%.*f' % (digits[1] if digits else 2, value)
        return str(value) if value not in (False, None) else '—'

    def _log_label(self):
        """'<b>[00004] ACABADO PPT</b> · N° 1 · [800116] SODA CAUSTICA'; las
        sub-líneas de colorantes llevan 'COLORANTES › producto'."""
        self.ensure_one()
        process = self._get_processes()[:1]
        holder = self.parent_line_id or self
        name = self.display_name
        if self.parent_line_id:
            name = '%s › %s' % (self.parent_line_id.display_name, name)
        return Markup('<b>%s</b> · N° %s · %s') % (
            process.base_process_id.display_name or _('Proceso'),
            holder.order_number or '', name)

    def _log_summary(self):
        self.ensure_one()
        if self.line_type == 'colorants' and not self.parent_line_id:
            return _('%s colorantes', len(self.child_ids))
        summary = '%s %s' % (self._log_value('factor'), self._log_value('uom'))
        if self.lot_id:
            summary = _('%(summary)s, lote %(lot)s',
                        summary=summary, lot=self.lot_id.display_name)
        return summary

    def _log_changes(self, before, fnames):
        suffix = _(' (recalculado por tabla)') \
            if self.env.context.get('table_recompute') else ''
        for rec in self:
            if rec.id not in before:
                continue
            changes = []
            for fname in fnames:
                old, new = before[rec.id][fname], rec._log_value(fname)
                if old != new:
                    changes.append(Markup('%s: %s → %s') % (
                        rec._fields[fname]._description_string(self.env), old, new))
            if changes:
                _queue_recipe_log(self.env, rec._log_owners(), Markup('%s: %s%s') % (
                    rec._log_label(), Markup('; ').join(changes), suffix))

    # ------------------------------------------------------------------
    # Motor de tablas (CF)
    # ------------------------------------------------------------------
    def _recompute_table_factors(self):
        """Recalcula el factor de las líneas CON TABLA: CF = suma de % de las
        líneas de COLORANTES del mismo proceso; si el proceso no tiene
        colorantes (p.ej. un preparado/lavado con sal), se usa el CF de TODA
        la receta — la sal se dosifica según el colorante del teñido aunque
        viva en otro proceso. Se busca el rango que contiene el CF y se toma
        su concentración. Las líneas con ajuste manual no se tocan."""
        # Un cambio de colorantes afecta también las tablas de los procesos
        # HERMANOS sin colorantes propios (dependen del CF de la receta).
        processes = self._get_processes()
        for proc in self._get_processes():
            processes |= proc._sibling_processes()
        for process in processes:
            cf = process._cf_sum() or process._sibling_processes()._cf_sum()
            for tl in process.color_recipe_process_line_ids.filtered(
                    lambda l: l.base_line_id.range_ids and not l.factor_manual):
                rng = tl.base_line_id.range_ids.filtered(
                    lambda r: r.percent_from <= cf <= r.percent_to)[:1]
                if rng and (tl.factor != rng.factor or tl.uom != rng.uom):
                    tl.with_context(table_recompute=True).write(
                        {'factor': rng.factor, 'uom': rng.uom})

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        if not self.env.context.get('table_recompute'):
            records._recompute_table_factors()
        if not self.env.context.get('skip_reseq'):
            records.color_recipe_process_id._resequence_lines()
        for rec in records:
            _queue_recipe_log(self.env, rec._log_owners(), Markup('%s: %s') % (
                rec._log_label(), _('línea agregada (%s)', rec._log_summary())))
        return records

    def write(self, vals):
        logged = [f for f in self._LOGGED_FIELDS if f in vals]
        before = {rec.id: {f: rec._log_value(f) for f in logged}
                  for rec in self} if logged else {}
        # Editar a mano el factor de una línea con tabla la marca como manual.
        if 'factor' in vals and not self.env.context.get('table_recompute') \
                and 'factor_manual' not in vals:
            manual = self.filtered(lambda l: l.base_line_id.range_ids)
            if manual:
                super(ColorRecipeProcessLine, manual).write({'factor_manual': True})
        res = super().write(vals)
        if logged:
            self._log_changes(before, logged)
        if not self.env.context.get('table_recompute') \
                and ({'factor', 'uom', 'product_id'} & set(vals.keys())):
            self._recompute_table_factors()
        if not self.env.context.get('skip_reseq') \
                and ({'sequence', 'order_number'} & set(vals.keys())):
            self.color_recipe_process_id._resequence_lines()
        return res

    def unlink(self):
        processes = self._get_processes()
        for rec in self:
            _queue_recipe_log(self.env, rec._log_owners(), Markup('%s: %s') % (
                rec._log_label(), _('línea eliminada (%s)', rec._log_summary())))
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