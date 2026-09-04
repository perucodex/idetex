# -*- coding: utf-8 -*-
"""Extensiones al modelo `mrp.routing.workcenter.operation` definidas en este
modulo (idtx_product_development).

Aqui viven:
- Campos de maquinaria: `general_machine_id` y `specific_machine_ids`
  (catálogo `texplus.machine`, hoy mantenido solo en Odoo).
- Smart button hacia las rutas (`base_process_ids` + `action_open_base_processes`).
- Cascada general -> específicas al crear/modificar la fase.
- Validación de uso en procesos base al eliminar (`_check_used_in_base_process`).

La sincronización hacia TEXPLUS (FASPRO/MAQFAS/PROLIN) se retiró en 2026-09:
Odoo es la única fuente de las fases y sus máquinas.
"""

import logging

from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class MrpRoutingWorkcenterOperation(models.Model):
    _inherit = 'mrp.routing.workcenter.operation'

    general_machine_id = fields.Many2one(
        'texplus.machine',
        string='Máquina General',
        domain="[('is_general','=',True)]",
        ondelete='restrict',
        help='Máquina general (tipo de máquina) con la que se ejecuta la fase.',
    )
    specific_machine_ids = fields.Many2many(
        'texplus.machine',
        'texplus_machine_operation_rel',
        'operation_id',
        'machine_id',
        string='Máquinas Específicas',
        help='Máquinas concretas asignadas a esta fase.',
    )
    base_process_ids = fields.Many2many(
        'mrp.base.process',
        string='Rutas que usan esta operacion',
        compute='_compute_base_process_ids',
        search='_search_base_process_ids',
    )
    base_process_count = fields.Integer(
        compute='_compute_base_process_ids',
    )

    @api.depends()
    def _compute_base_process_ids(self):
        Line = self.env['mrp.base.process.line']
        for record in self:
            lines = Line.sudo().search([('operation_id', '=', record.id)])
            processes = lines.mapped('mrp_base_process_id')
            record.base_process_ids = processes
            record.base_process_count = len(processes)

    @api.model
    def _search_base_process_ids(self, operator, value):
        Line = self.env['mrp.base.process.line']
        processes = self.env['mrp.base.process'].search([('id', operator, value)])
        lines = Line.search([('mrp_base_process_id', 'in', processes.ids)])
        return [('id', 'in', lines.mapped('operation_id').ids)]

    def action_open_base_processes(self):
        """Abre la lista de mrp.base.process que contienen esta operacion."""
        self.ensure_one()
        return self.base_process_ids._get_records_action(
            name='Rutas con "%s"' % (self.name or ''),
        )

    @api.onchange('general_machine_id')
    def _onchange_general_machine_id(self):
        Machine = self.env['texplus.machine']
        for record in self:
            if not record.general_machine_id:
                continue
            # ADITIVO: solo se AGREGAN las especificas de esta general que
            # falten. NO se eliminan las maquinas ya asignadas para respetar la
            # curacion manual. El usuario puede quitar las que no quiera.
            specifics = Machine.search([
                ('is_general', '=', False),
                ('general_machine_id', '=', record.general_machine_id.id),
            ])
            missing = specifics - record.specific_machine_ids
            if missing:
                record.specific_machine_ids = record.specific_machine_ids | missing

    def _ensure_specific_machines_from_general(self):
        """Add every specific machine that belongs to the operation's
        `general_machine_id`. Does NOT remove machines that may already
        be linked but belong to a different general — use
        `_resync_specifics_with_general` for the full cascade.

        Returns True if anything was added, False otherwise.
        """
        Machine = self.env['texplus.machine'].sudo()
        changed = False
        for op in self:
            if not op.general_machine_id:
                continue
            specifics = Machine.search([
                ('is_general', '=', False),
                ('general_machine_id', '=', op.general_machine_id.id),
            ])
            if not specifics:
                continue
            existing = op.specific_machine_ids
            missing = specifics - existing
            if missing:
                op.with_context(skip_machine_cascade=True).write({
                    'specific_machine_ids': [(4, m.id) for m in missing],
                })
                changed = True
        return changed

    def _resync_specifics_with_general(self):
        """Replace `specific_machine_ids` with EXACTLY the specifics that
        belong to `general_machine_id`. Used when the general changes —
        drops machines tied to the previous general (cascade out) and
        adds the new general's specifics (cascade in) in one write.

        When `general_machine_id` is empty, clears `specific_machine_ids`.
        Returns True if the resulting set differs from the original.
        """
        Machine = self.env['texplus.machine'].sudo()
        changed = False
        for op in self:
            if op.general_machine_id:
                specifics = Machine.search([
                    ('is_general', '=', False),
                    ('general_machine_id', '=', op.general_machine_id.id),
                ])
                target_ids = set(specifics.ids)
            else:
                target_ids = set()
            current_ids = set(op.specific_machine_ids.ids)
            if target_ids == current_ids:
                continue
            op.with_context(skip_machine_cascade=True).write({
                'specific_machine_ids': [(6, 0, list(target_ids))],
            })
            changed = True
        return changed

    @api.onchange('specific_machine_ids')
    def _onchange_specific_machine_ids_set_general(self):
        for record in self:
            if record.general_machine_id:
                continue
            generals = record.specific_machine_ids.mapped('general_machine_id')
            if len(generals) == 1:
                record.general_machine_id = generals

    def _check_used_in_base_process(self):
        line_model = self.env['mrp.base.process.line'].sudo()
        blocked = {}
        for operation in self:
            lines = line_model.search([('operation_id', '=', operation.id)])
            if lines:
                blocked[operation] = lines.mapped('mrp_base_process_id')
        return blocked

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        if not self.env.context.get('skip_machine_cascade'):
            records._ensure_specific_machines_from_general()
        return records

    def write(self, vals):
        # Snapshot de la máquina general ANTES de escribir para saber qué
        # registros la cambiaron y completar sus específicas (aditivo).
        general_swapped = self.browse()
        if 'general_machine_id' in vals:
            new_general_id = vals.get('general_machine_id') or False
            general_swapped = self.filtered(
                lambda r: (r.general_machine_id.id or False) != new_general_id
            )

        result = super().write(vals)
        if self.env.context.get('skip_machine_cascade'):
            return result
        if general_swapped:
            general_swapped._ensure_specific_machines_from_general()
        return result

    def unlink(self):
        if not self:
            return super().unlink()

        used_in_odoo = self._check_used_in_base_process()
        if used_in_odoo:
            details = '\n'.join(
                '- %s: %s' % (op.name, ', '.join(processes.mapped('name')))
                for op, processes in used_in_odoo.items()
            )
            raise UserError(
                'No se puede eliminar las siguientes fases porque estan en uso '
                'en procesos base de Odoo:\n%s' % details
            )
        return super().unlink()
