# -*- coding: utf-8 -*-
from odoo import models, _


class TechnicalSheet(models.Model):
    _inherit = 'technical.sheet'

    def action_open_voucher_ubicacion(self):
        """Abre el wizard para ubicar (ALBDET.ALRPIELOC) las piezas de un
        voucher según la talla. Solo tiene sentido para productos rectos."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Ubicar piezas por talla (TEXPLUS)'),
            'res_model': 'voucher.ubicacion.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_technical_sheet_id': self.id},
        }
