# -*- coding: utf-8 -*-

from odoo import models 
from odoo.exceptions import UserError

class MaintenanceRequest(models.Model):
    _inherit = 'maintenance.request'

    def write(self, vals):
        for rec in self:
            if 'stage_id' in vals:
                # new_stage = self.env['maintenance.stage'].browse(vals['stage_id'])
                if rec.stage_id.done and not self.archive:
                    raise UserError("No puedes mover una solicitud finalizada.")
        return super().write(vals)