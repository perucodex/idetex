# -*- coding: utf-8 -*-

from odoo import api, Command, fields, models, _
from odoo.exceptions import UserError, ValidationError

class MrpWorkorderBatch(models.Model):
    _name = 'mrp.workorder.batch'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Mrp Workorder Batch'

    # workorder_id = fields.Many2one('mrp.workorder', string='Workorder')
    sequence = fields.Integer('Sequence')
    name = fields.Char('Name', required=True, copy=False, readonly=False, default=lambda self: _('New'))
    batch_date = fields.Date('Batch Date', required=True, default=lambda self: fields.Date.context_today(self))
    wo_roll_ids = fields.Many2many('mrp.workorder.roll', string='Batch Rolls')
    total_weight = fields.Float('Total', compute='_compute_total_weight')
    mrwo_id = fields.Many2one('mrp.routing.workcenter.operation', string='Last Operation')
    state = fields.Selection([
        ('draft', 'Draft'),
        ('batch', 'Batch'),
        ('split', 'Dividida'),
        ('unbuild', 'Unbuild'),
    ], string='State', default='draft')

    # --- Genealogía de división (sublotes ISA-95: la partida padre es el
    # registro del teñido; las hijas heredan sus propiedades y siguen rutas
    # separadas, identificadas como <padre>-A, <padre>-B, ...) ---
    parent_batch_id = fields.Many2one(
        'mrp.workorder.batch', string='Partida Origen', readonly=True,
        index=True, ondelete='restrict', copy=False,
        help='Partida de teñido de la que se dividió esta sub-partida.')
    split_code = fields.Char('Sub-partida', readonly=True, copy=False,
                             help='Código del grupo dentro de la partida original (A, B, ...).')
    child_batch_ids = fields.One2many(
        'mrp.workorder.batch', 'parent_batch_id', string='Sub-partidas')
    child_count = fields.Integer(compute='_compute_child_count')
    origin_roll_ids = fields.Many2many(
        'mrp.workorder.roll', string='Rollos Originales',
        compute='_compute_origin_roll_ids',
        help='Composición original de la partida dividida: los rollos que hoy '
             'viven en sus sub-partidas (recursivo si estas se volvieron a dividir).')

    def _compute_origin_roll_ids(self):
        for rec in self:
            rolls = rec.wo_roll_ids
            seen = self.browse()
            children = rec.child_batch_ids
            while children:
                rolls |= children.wo_roll_ids
                seen |= children
                children = children.child_batch_ids - seen
            rec.origin_roll_ids = rolls

    def _compute_child_count(self):
        for rec in self:
            rec.child_count = len(rec.child_batch_ids)

    def _compute_total_weight(self):
        for rec in self:
            if rec.wo_roll_ids:
                rec.total_weight = sum(rec.wo_roll_ids.mapped('gross_weight'))
            elif rec.child_batch_ids:
                # Partida dividida: el total histórico es la suma de sus hijas.
                rec.total_weight = sum(
                    rec.child_batch_ids.wo_roll_ids.mapped('gross_weight'))
            else:
                rec.total_weight = 0

    @api.constrains('wo_roll_ids')
    def _check_same_color_recipe(self):
        """Una partida solo puede agrupar rollos de órdenes de fabricación con la
        MISMA receta de color (se tiñe todo junto). Aplica a cualquier vía de
        armado: formulario de Partidas, taller (dye batch), etc."""
        for batch in self:
            productions = batch.wo_roll_ids.workorder_id.production_id
            by_recipe = {}
            for prod in productions:
                by_recipe.setdefault(prod.color_recipe_id, self.env['mrp.production'])
                by_recipe[prod.color_recipe_id] |= prod
            if len(by_recipe) > 1:
                detail = '\n'.join(
                    '- %s: %s' % (
                        recipe.display_name if recipe else _('(sin receta de color)'),
                        ', '.join(prods.mapped('name')),
                    )
                    for recipe, prods in by_recipe.items()
                )
                raise ValidationError(_(
                    'La partida %(batch)s no puede mezclar órdenes de fabricación '
                    'con recetas de color distintas:\n%(detail)s',
                    batch=batch.name, detail=detail,
                ))
    
    #=== CRUD METHODS ===#

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _("New")) == _("New"):
                seq_date = fields.Datetime.context_timestamp(
                    self, fields.Datetime.to_datetime(vals['batch_date'])
                ) if 'batch_date' in vals else None
                vals['name'] = self.env['ir.sequence'].with_company(vals.get('company_id')).next_by_code(
                    'mrp.workorder.batch', sequence_date=seq_date) or _("New")

        return super().create(vals_list)
    
    def clear_rolls(self):
        workorders = self.wo_roll_ids.mapped('workorder_id')
        self.wo_roll_ids = [Command.clear()]
        workorders._sync_textile_qty_produced()
    
    def create_batch(self):
        for rec in self:
            if any(roll.in_batch for roll in rec.wo_roll_ids):
                raise UserError(_('Some rolls are in other batch, please select rolls again.'))
            rec.wo_roll_ids.write({'in_batch': True})
            rec.state = 'batch'
            rec.wo_roll_ids.mapped('workorder_id')._sync_textile_qty_produced()

    def unbuild_batch(self):
        # if self.workorder_id:
        #     raise UserError(_('Can\'t unbild a batch already in use, production %s.') %self.workorder_id.production_id.name)
        for rec in self:
            rec.wo_roll_ids.write({'in_batch': False})
            rec.state = 'unbuild'
            rec.wo_roll_ids.mapped('workorder_id')._sync_textile_qty_produced()

    def rebuild_batch(self):
        for rec in self:
            if any(roll.in_batch for roll in rec.wo_roll_ids):
                raise UserError(_('Some rolls are in other batch, can\'t rebuild batch.'))
            rec.wo_roll_ids.write({'in_batch': True})
            rec.state = 'batch'
            rec.wo_roll_ids.mapped('workorder_id')._sync_textile_qty_produced()

    # ------------------------------------------------------------------
    # División de partida (sublotes)
    # ------------------------------------------------------------------
    def action_open_split_wizard(self):
        self.ensure_one()
        if self.state != 'batch':
            raise UserError(_('Solo se puede dividir una partida confirmada.'))
        if len(self.wo_roll_ids) < 2:
            raise UserError(_('La partida necesita al menos 2 rollos para dividirse.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Dividir partida %s') % self.name,
            'res_model': 'mrp.workorder.batch.split',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_batch_id': self.id},
        }

    def _apply_split(self, groups):
        """Divide la partida en sub-partidas <nombre>-<código>.

        `groups` = {código: recordset de rollos}. Reglas: todos los rollos de la
        partida quedan asignados a exactamente un grupo y hay al menos 2 grupos.
        El padre conserva el nombre y el registro del teñido (pasa a estado
        'Dividida', sin rollos propios: su composición histórica es la unión de
        sus hijas). Las hijas heredan fecha/última operación y siguen su ruta
        por separado.
        """
        self.ensure_one()
        if self.state != 'batch':
            raise UserError(_('Solo se puede dividir una partida confirmada.'))
        groups = {
            (code or '').strip().upper(): rolls
            for code, rolls in groups.items() if rolls
        }
        if len(groups) < 2:
            raise UserError(_('La división requiere al menos 2 grupos con rollos.'))
        union = self.env['mrp.workorder.roll']
        total = 0
        for rolls in groups.values():
            union |= rolls
            total += len(rolls)
        if union != self.wo_roll_ids or total != len(self.wo_roll_ids):
            raise UserError(_(
                'Todos los rollos de la partida deben quedar asignados a '
                'exactamente un grupo (sin repetidos ni faltantes).'))

        children = self.env['mrp.workorder.batch']
        for code in sorted(groups):
            name = '%s-%s' % (self.name, code)
            if self.search_count([('name', '=', name)]):
                raise UserError(_('Ya existe una partida con el nombre %s.') % name)
            children |= self.create([{
                'name': name,
                'parent_batch_id': self.id,
                'split_code': code,
                'batch_date': self.batch_date,
                'mrwo_id': self.mrwo_id.id,
                'state': 'batch',
                'wo_roll_ids': [Command.set(groups[code].ids)],
            }])
        # El padre queda como registro histórico del teñido (sin rollos propios;
        # los rollos siguen in_batch=True porque viven en las hijas).
        self.wo_roll_ids = [Command.clear()]
        self.state = 'split'
        self.message_post(body=_(
            'Partida dividida en: %s') % ', '.join(children.mapped('name')))
        for child in children:
            child.message_post(body=_(
                'Sub-partida creada por división de %s (teñida junto a %s).') % (
                self.name, ', '.join((children - child).mapped('name'))))
        return children

    def action_view_children(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Sub-partidas de %s') % self.name,
            'res_model': 'mrp.workorder.batch',
            'view_mode': 'list,form',
            'domain': [('parent_batch_id', '=', self.id)],
        }

    def action_view_parent(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'mrp.workorder.batch',
            'res_id': self.parent_batch_id.id,
            'view_mode': 'form',
        }