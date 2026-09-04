# -*- coding: utf-8 -*-
"""Extensiones al modelo `mrp.routing.workcenter.operation` definidas en este
modulo (idtx_product_development).

- Smart button hacia las rutas (`base_process_ids` + `action_open_base_processes`).
- Validación de uso en procesos base al eliminar (`_check_used_in_base_process`).

El código FASPRO (fas_code), la máquina general y las máquinas específicas eran
el espejo de TEXPLUS y se retiraron en 2026-09.
"""

import logging

from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class MrpRoutingWorkcenterOperation(models.Model):
    _inherit = 'mrp.routing.workcenter.operation'

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

    def _check_used_in_base_process(self):
        line_model = self.env['mrp.base.process.line'].sudo()
        blocked = {}
        for operation in self:
            lines = line_model.search([('operation_id', '=', operation.id)])
            if lines:
                blocked[operation] = lines.mapped('mrp_base_process_id')
        return blocked

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
