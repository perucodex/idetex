# -*- coding: utf-8 -*-
from odoo import fields, models


class ThreadCodeReturnWizard(models.TransientModel):
    _name = 'idtx.thread.code.return.wizard'
    _description = 'Confirmación de revertir hilado (borrado definitivo)'

    thread_code_id = fields.Many2one('idtx.thread.code', string='Hilado', required=True, ondelete='cascade')

    def action_confirm(self):
        """Segunda confirmación: ejecuta el borrado definitivo (producto + SITPRO)."""
        self.ensure_one()
        return self.thread_code_id.action_return()
