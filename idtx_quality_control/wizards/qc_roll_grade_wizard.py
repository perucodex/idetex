# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class QcRollGradeWizard(models.TransientModel):
    """Calificación previa de los rollos de la partida por N° de rollo
    (1..N, la numeración de Acabado), antes del pesado. Genera una fila por
    rollo y guarda las marcas (qc.roll.hold) que usa la zona de pesado."""
    _name = 'qc.roll.grade.wizard'
    _description = 'Calificar rollos de la partida (previo al pesado)'

    batch_id = fields.Many2one('mrp.workorder.batch', string='Partida', required=True, readonly=True)
    roll_count = fields.Integer(
        'Cantidad de rollos', required=True,
        help='N° de rollos de la partida según la numeración de Acabado.')
    line_ids = fields.One2many('qc.roll.grade.wizard.line', 'wizard_id', string='Rollos')
    default_grade = fields.Selection(
        [('A', 'A'), ('B', 'B'), ('M', 'M')], string='Grado para los no marcados',
        help='Si se indica, las filas sin grado ni separación se guardan con este grado.')

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        batch_id = res.get('batch_id') or self.env.context.get('default_batch_id')
        if batch_id:
            batch = self.env['mrp.workorder.batch'].browse(batch_id)
            count = res.get('roll_count') or batch._roll_grade_default_count()
            res['roll_count'] = count
            res['line_ids'] = [(0, 0, vals) for vals in batch._roll_grade_wizard_lines(count)]
        return res

    def action_regenerate(self):
        """Vuelve a generar las filas con la cantidad indicada (conserva lo ya marcado)."""
        self.ensure_one()
        if self.roll_count <= 0:
            raise UserError(_('Indica la cantidad de rollos.'))
        current = {l.roll_num: l for l in self.line_ids}
        vals = []
        for line_vals in self.batch_id._roll_grade_wizard_lines(self.roll_count):
            old = current.get(line_vals['roll_num'])
            if old:
                line_vals.update({'grade': old.grade, 'observed': old.observed,
                                  'reason': old.reason, 'note': old.note})
            vals.append((0, 0, line_vals))
        self.line_ids = [(5, 0, 0)] + vals
        return {'type': 'ir.actions.act_window', 'res_model': self._name, 'res_id': self.id,
                'view_mode': 'form', 'target': 'new'}

    def action_apply(self):
        self.ensure_one()
        Hold = self.env['qc.roll.hold']
        holds = {h.roll_num: h for h in self.batch_id.roll_hold_ids}
        # Los campos informativos de la fila son readonly y el cliente no los
        # envía: la situación real del rollo se consulta en el servidor.
        released_nums = set(self.batch_id.finished_roll_ids.filtered('quality_released').mapped('roll_num'))
        applied = 0
        for line in self.line_ids:
            if not line.roll_num:
                continue
            grade = line.grade
            observed = line.observed
            released = line.roll_num in released_nums
            if not grade and not observed and self.default_grade and not released:
                grade = self.default_grade
            if not grade and not observed:
                continue
            if released:
                continue  # ya recibido por almacén: no se cambia
            vals = {'grade': False if observed else grade, 'observed': observed,
                    'reason': line.reason if observed else False, 'note': line.note or False}
            hold = holds.get(line.roll_num)
            if hold:
                if hold.state == 'cancel':
                    vals['state'] = 'open'
                hold.write(vals)
            else:
                vals.update({'batch_id': self.batch_id.id, 'roll_num': line.roll_num})
                Hold.create(vals)
            applied += 1
        self.batch_id.message_post(body=_(
            'Calificación previa de rollos: %(n)s rollo(s) marcados por %(user)s.',
            n=applied, user=self.env.user.name))
        return {'type': 'ir.actions.act_window_close'}


class QcRollGradeWizardLine(models.TransientModel):
    _name = 'qc.roll.grade.wizard.line'
    _description = 'Fila de calificación previa de rollo'
    _order = 'roll_num'

    wizard_id = fields.Many2one('qc.roll.grade.wizard', required=True, ondelete='cascade')
    # readonly solo en la vista (con force_save): si el campo es readonly en el
    # modelo el cliente web no lo envía al guardar y falla el required.
    roll_num = fields.Integer('N° rollo', required=True)
    grade = fields.Selection([('A', 'A'), ('B', 'B'), ('M', 'M')], string='Grado')
    observed = fields.Boolean('Separar')
    reason = fields.Selection(
        [('stain', 'Desmanchar'), ('decontaminate', 'Descontaminar'),
         ('reprocess', 'Reprocesar'), ('other', 'Otro')], string='Motivo')
    note = fields.Char('Detalle')
    # situación actual del rollo (solo lectura)
    lot_name = fields.Char('Lote pesado', readonly=True)
    weight = fields.Float('Kg', readonly=True)
    current_state = fields.Char('Estado actual', readonly=True)
    released = fields.Boolean('Liberado', readonly=True)

    @api.onchange('observed')
    def _onchange_observed(self):
        if self.observed:
            self.grade = False
            if not self.reason:
                self.reason = 'stain'
        else:
            self.reason = False

    @api.onchange('grade')
    def _onchange_grade(self):
        if self.grade:
            self.observed = False
            self.reason = False
