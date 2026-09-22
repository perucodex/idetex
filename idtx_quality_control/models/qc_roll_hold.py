# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class QcRollHold(models.Model):
    """CALIFICACIÓN PREVIA de un rollo de la partida, por el N° de rollo que
    Acabado marca (1..N), registrada por Calidad al hacer su informe ANTES
    del pesado. Puede ser:

    * un GRADO (A/B/M): al pesar ese N°, el rollo nace con ese grado;
    * SEPARAR para reproceso (motivo + detalle): al pesar nace OBSERVADO,
      con sticker OBSERVADO; Calidad le da el grado final después y la zona
      de pesado lo repesa.

    Si el N° ya fue pesado, la marca se aplica al rollo de inmediato."""
    _name = 'qc.roll.hold'
    _description = 'Calificación previa de rollo (calidad)'
    _order = 'batch_id desc, roll_num'
    _rec_name = 'display_name'

    batch_id = fields.Many2one(
        'mrp.workorder.batch', string='Partida', required=True, ondelete='cascade', index=True)
    roll_num = fields.Integer('N° rollo', required=True)
    grade = fields.Selection(
        [('A', 'A'), ('B', 'B'), ('M', 'M')], string='Grado',
        help='Grado que recibirá el rollo al pesarse. Vacío si se separa para reproceso.')
    observed = fields.Boolean(
        'Separar para reproceso',
        help='El rollo se pesa como OBSERVADO y va al área de reproceso; el grado se da después.')
    reason = fields.Selection(
        [('stain', 'Desmanchar'), ('decontaminate', 'Descontaminar'),
         ('reprocess', 'Reprocesar'), ('other', 'Otro')],
        string='Motivo')
    note = fields.Char('Detalle')
    state = fields.Selection(
        [('open', 'Por pesar'), ('weighed', 'Aplicado al rollo'),
         ('resolved', 'Resuelto'), ('cancel', 'Anulado')],
        string='Estado', default='open', required=True, index=True, readonly=True)
    roll_id = fields.Many2one('mrp.production.roll', string='Rollo pesado', readonly=True)
    roll_grade = fields.Selection(related='roll_id.quality_grade', string='Grado final')
    user_id = fields.Many2one('res.users', 'Registrado por', default=lambda s: s.env.uid, readonly=True)
    date = fields.Datetime('Fecha', default=fields.Datetime.now, readonly=True)
    company_id = fields.Many2one(related='batch_id.company_id', store=True)

    _uniq_batch_roll = models.Constraint(
        'unique(batch_id, roll_num)', 'Ese N° de rollo ya tiene calificación previa en la partida.')

    @api.depends('batch_id.name', 'roll_num')
    def _compute_display_name(self):
        for hold in self:
            hold.display_name = '%s · rollo %s' % (hold.batch_id.name or '', hold.roll_num or '')

    @api.constrains('roll_num', 'grade', 'observed', 'reason')
    def _check_mark(self):
        for hold in self:
            if hold.roll_num <= 0:
                raise ValidationError(_('El N° de rollo debe ser mayor que cero.'))
            if not hold.grade and not hold.observed:
                raise ValidationError(_(
                    'Rollo N° %s: indica el grado (A, B o M) o marca "Separar para reproceso".'
                ) % hold.roll_num)
            if hold.observed and not hold.reason:
                raise ValidationError(_('Rollo N° %s: indica el motivo de la separación.') % hold.roll_num)

    @api.onchange('observed')
    def _onchange_observed(self):
        if self.observed:
            self.grade = False
            if not self.reason:
                self.reason = 'stain'
        else:
            self.reason = False

    @api.model_create_multi
    def create(self, vals_list):
        holds = super().create(vals_list)
        holds._apply_to_weighed_roll()
        return holds

    def write(self, vals):
        res = super().write(vals)
        if {'grade', 'observed', 'reason', 'note'} & set(vals):
            self._apply_to_weighed_roll()
        return res

    def action_cancel(self):
        self.filtered(lambda h: h.state == 'open').write({'state': 'cancel'})
        return True

    def action_reopen(self):
        holds = self.filtered(lambda h: h.state == 'cancel')
        holds.write({'state': 'open'})
        holds._apply_to_weighed_roll()
        return True

    def _apply_to_weighed_roll(self):
        """Si el N° de rollo YA fue pesado, la calificación previa se aplica al
        rollo de inmediato (grado, o pasa a OBSERVADO). Rollos liberados a
        almacén no se tocan."""
        Roll = self.env['mrp.production.roll']
        for hold in self.filtered(lambda h: h.state in ('open', 'weighed')):
            roll = hold.roll_id or Roll.search([
                ('batch_id', '=', hold.batch_id.id), ('roll_num', '=', hold.roll_num),
                ('lot_id', '!=', False)], limit=1)
            if not roll:
                continue
            if roll.quality_released:
                raise ValidationError(_(
                    'El rollo N° %(num)s (%(lot)s) ya fue liberado a almacén: no se puede '
                    'cambiar su calificación.', num=hold.roll_num, lot=roll.lot_id.name))
            if hold.observed:
                roll.write({'quality_grade': False, 'quality_observation': hold.reason,
                            'quality_note': hold.note or roll.quality_note or False,
                            'reweigh_pending': False})
            else:
                vals = {'quality_grade': hold.grade}
                if hold.note:
                    vals['quality_note'] = hold.note
                roll.write(vals)
            hold.write({'roll_id': roll.id, 'state': 'weighed'})
            if roll.hold_id != hold:
                roll.hold_id = hold

    def _reason_label(self):
        self.ensure_one()
        return dict(self._fields['reason']._description_selection(self.env)).get(self.reason, '')

    def _mark_label(self):
        """Texto corto para informes y lista: 'Grado B' / 'Separar: Desmanchar'."""
        self.ensure_one()
        if self.observed:
            return _('Separar: %s') % self._reason_label()
        return _('Grado %s') % (self.grade or '')
