# -*- coding: utf-8 -*-

from odoo import api, fields, models

class AccountMove(models.Model):
    _inherit = 'account.move'

    idtx_oc_ref = fields.Char(string='N° O. Compra')

    @api.depends('state', 'move_type')
    def _compute_display_send_button(self):
        super()._compute_display_send_button()
        for move in self:
            if move.is_sale_document() and move.state in ('posted', 'cancel'):
                move.display_send_button = True
