# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class RollTransfer(models.TransientModel):
    _name = 'mrp.workorder.roll.transfer'
    _description = 'Transferir Rollos entre OTs'

    roll_ids = fields.Many2many(
        'mrp.workorder.roll', 'roll_transfer_wizard_rel', 'wizard_id', 'roll_id',
        string='Rollos a Transferir', readonly=True)
    product_tmpl_id = fields.Many2one(
        'product.template', string='Producto', compute='_compute_from_rolls')
    source_workorder_ids = fields.Many2many(
        'mrp.workorder', 'roll_transfer_wizard_src_rel', 'wizard_id', 'wo_id',
        string='OTs de Origen', compute='_compute_from_rolls')
    dest_workorder_id = fields.Many2one(
        'mrp.workorder', string='OT de Destino', required=True)

    @api.depends('roll_ids')
    def _compute_from_rolls(self):
        for w in self:
            w.product_tmpl_id = w.roll_ids.mapped('product_id')[:1]
            w.source_workorder_ids = w.roll_ids.mapped('workorder_id')

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        # Solo se abre desde la lista de Rollos con registros seleccionados.
        rolls = self.env['mrp.workorder.roll'].browse(
            self.env.context.get('active_ids', [])).exists()
        if self.env.context.get('active_model') == 'mrp.workorder.roll' or rolls:
            if not rolls:
                raise UserError(_('Selecciona al menos un rollo a transferir.'))
            # No se pueden transferir rollos que ya están en una partida activa
            # (estado "Partida"): romperían la composición de la partida.
            self._check_rolls_not_in_batch(rolls)
            # Todos los rollos deben ser del MISMO producto.
            tmpls = rolls.mapped('product_id')
            if len(tmpls) > 1:
                raise UserError(_(
                    'Los rollos seleccionados tienen productos distintos:\n%s\n\n'
                    'Solo se pueden transferir juntos rollos del MISMO producto.'
                ) % '\n'.join('- %s' % t.display_name for t in tmpls))
            res['roll_ids'] = [(6, 0, rolls.ids)]
        return res

    @api.model
    def _check_rolls_not_in_batch(self, rolls):
        in_batch = rolls.filtered(lambda r: r.current_batch_id)
        if in_batch:
            raise UserError(_(
                'No se pueden transferir rollos que ya están en una partida '
                '(estado "Partida"):\n%s'
            ) % '\n'.join(
                '- %s (partida %s)' % (r.name, r.current_batch_id.name)
                for r in in_batch))

    def action_transfer(self):
        self.ensure_one()
        rolls = self.roll_ids
        dest = self.dest_workorder_id
        if not rolls:
            raise UserError(_('No hay rollos a transferir.'))
        self._check_rolls_not_in_batch(rolls)
        if dest in rolls.mapped('workorder_id'):
            raise UserError(_('La OT de destino no puede ser la misma OT del rollo.'))
        for roll in rolls:
            if roll.transfer_state == 'recibido':
                raise UserError(_(
                    'El rollo %s ya es un registro RECIBIDO; no se puede volver '
                    'a transferir.') % roll.name)
            # Original en la OT de tejido: queda TRANSFERIDO (sigue contando su
            # consumo). Copia en la OT destino: RECIBIDO (no cuenta consumo),
            # mismo número de rollo, enlazada al original.
            roll.write({'transfer_state': 'transferido', 'dest_workorder_id': dest.id})
            roll.with_context(skip_roll_option_check=True).copy({
                'name': roll.name,
                'workorder_id': dest.id,
                'transfer_state': 'recibido',
                'transfer_origin_roll_id': roll.id,
                'dest_workorder_id': False,
                'in_batch': False,
            })
        if dest.production_id:
            dest.production_id.message_post(body=_(
                'Rollos recibidos por transferencia en %(dst)s: %(rolls)s',
                dst=dest.mrwo_id.name or dest.display_name,
                rolls=', '.join(rolls.mapped('name'))))
        for wo in rolls.mapped('workorder_id'):
            if wo.production_id:
                wo.production_id.message_post(body=_(
                    'Rollos transferidos de %(src)s a %(dst)s: %(rolls)s',
                    src=wo.mrwo_id.name or wo.display_name,
                    dst=dest.mrwo_id.name or dest.display_name,
                    rolls=', '.join(rolls.filtered(lambda r: r.workorder_id == wo).mapped('name'))))
        return {'type': 'ir.actions.act_window_close'}
