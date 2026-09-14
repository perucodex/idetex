# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class MrpProductionRoll(models.Model):
    """Calificación de calidad del rollo TERMINADO (después del último
    proceso y del pesado). El grado define la ubicación a la que entra el
    rollo cuando almacén lo recibe: A → Existencias, B → Saldo, M → Mermas."""
    _inherit = 'mrp.production.roll'

    quality_grade = fields.Selection(
        [('A', 'A'), ('B', 'B'), ('M', 'M')], string='Grado', copy=False, index=True,
        help='A: primera (Existencias) · B: segunda (Saldo) · M: merma (Mermas).')
    quality_observation = fields.Selection(
        [('stain', 'Desmanchar'), ('decontaminate', 'Descontaminar'),
         ('reprocess', 'Reprocesar'), ('other', 'Otro')],
        string='Observación', copy=False,
        help='Motivo por el que el rollo queda retenido hasta darle grado.')
    quality_note = fields.Char('Nota de calidad', copy=False)
    quality_state = fields.Selection(
        [('pending', 'Por evaluar'), ('observed', 'Observado'),
         ('graded', 'Calificado'), ('released', 'Liberado')],
        string='Estado calidad', compute='_compute_quality_state', store=True, index=True)
    quality_released = fields.Boolean('Liberado a almacén', copy=False, readonly=True)
    quality_release_date = fields.Datetime('Fecha de liberación', copy=False, readonly=True)
    quality_user_id = fields.Many2one('res.users', 'Calificado por', copy=False, readonly=True)
    quality_date = fields.Datetime('Fecha de calificación', copy=False, readonly=True)

    @api.depends('quality_grade', 'quality_observation', 'quality_released')
    def _compute_quality_state(self):
        for roll in self:
            if roll.quality_released:
                roll.quality_state = 'released'
            elif roll.quality_grade:
                roll.quality_state = 'graded'
            elif roll.quality_observation:
                roll.quality_state = 'observed'
            else:
                roll.quality_state = 'pending'

    @api.constrains('quality_grade', 'quality_observation')
    def _check_quality_on_weighed_roll(self):
        for roll in self:
            if (roll.quality_grade or roll.quality_observation) and not roll.lot_id:
                raise ValidationError(_(
                    'El rollo %s no está pesado: primero se pesa y luego se califica.'
                ) % (roll.name or roll.id))

    def write(self, vals):
        quality_keys = {'quality_grade', 'quality_observation', 'quality_note'}
        if quality_keys & set(vals):
            released = self.filtered('quality_released')
            if released and ('quality_grade' in vals or 'quality_observation' in vals):
                raise UserError(_(
                    'Rollos ya liberados a almacén, no se puede cambiar su calificación: %s'
                ) % ', '.join(released.mapped('lot_id.name')))
            if vals.get('quality_grade') or vals.get('quality_observation'):
                vals.setdefault('quality_user_id', self.env.uid)
                vals.setdefault('quality_date', fields.Datetime.now())
        return super().write(vals)

    def action_set_grade(self):
        """Botones A / B / M de la lista de calificación (grado en contexto)."""
        grade = self.env.context.get('grade')
        if grade not in ('A', 'B', 'M'):
            raise UserError(_('Grado inválido.'))
        self.write({'quality_grade': grade})
        return True

    def action_clear_grade(self):
        self.filtered(lambda r: not r.quality_released).write({'quality_grade': False})
        return True
